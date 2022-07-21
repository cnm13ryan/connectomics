# coding=utf-8
# Copyright 2022 The Google Research Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Base class encapsulating processing a subvolume to another subvolume."""

import collections
import dataclasses
import enum
import importlib
from typing import Any, Tuple, Optional, Union

from connectomics.common import array
from connectomics.common import bounding_box
from connectomics.volume import descriptor
from connectomics.volume import subvolume
import dataclasses_json
import numpy as np

ImmutableArray = array.ImmutableArray
MutableArray = array.MutableArray
Subvolume = subvolume.Subvolume
SuggestedXyz = collections.namedtuple('SuggestedXyz', 'x y z')
TupleOrSuggestedXyz = Union['XyzTuple', SuggestedXyz]  # pylint: disable=invalid-name
XyzTuple = array.Tuple3i


@dataclasses.dataclass
class SubvolumeProcessorConfig(dataclasses_json.DataClassJsonMixin):
  """Configuration for a given subvolume processor."""
  # Name of class exposed in module_search_path.
  name: str

  # Arguments to SubvolumeProcessor, passed in as kwargs.
  args: Optional[dict[str, Any]] = None

  # Fully.qualified.python.module to search for SubvolumeProcessor `name`.
  module_search_path: str = 'connectomics.volume.processor'


@dataclasses.dataclass
class ProcessVolumeConfig(dataclasses_json.DataClassJsonMixin):
  """User-supplied configuration."""

  # Input volume to process.
  input_volume: descriptor.VolumeDescriptor

  # Output volume. Note that only TensorStore is currently supported. The
  # "metadata" field of the TensorStore spec should not be populated, as it is
  # automatically filled in by the processor.
  output_volume: descriptor.VolumeDescriptor

  # Output directory to write the volumetric data, inserted automatically into
  # the output_volume's TensorStore spec.
  output_dir: str

  # Bounding boxes to process.
  bounding_boxes: list[bounding_box.BoundingBox]

  # Processor configuration to apply.
  processor: SubvolumeProcessorConfig

  # Size of each subvolume to process.
  subvolume_size: array.Tuple3i = dataclasses.field(
      metadata=dataclasses_json.config(decoder=tuple))

  # Amount of overlap between processed subvolumes. This is independent of any
  # additional context required by individual processors.
  overlap: array.Tuple3i = dataclasses.field(
      metadata=dataclasses_json.config(decoder=tuple))

  # Number of bounding boxes to batch together per work item during processing.
  batch_size: int = 1

  # TODO(timblakely): Support back shifting edge boxes.

  # TODO(timblakely): Support expanding underlying tensorstore bounds so that end
  # chunks can be fully processed.


class OutputNums(enum.Enum):
  SINGLE = 1
  MULTI = 2


class SubvolumeProcessor:
  """Abstract base class for processors.

  The self.process method does the work.  The rest is for documenting input /
  output requirements and naming.
  """

  # Effective subvolume/overlap configuration as set by the framework within
  # which this processor is being executed. This might include, e.g. user
  # overrides supplied via command-line arguments.
  _context: ImmutableArray
  _subvol_size: ImmutableArray
  _overlap: ImmutableArray

  # Whether the output of this processor will be cropped for subvolumes that
  # are adjacent to the input bounding box(es).
  crop_at_borders = True

  # If true, the actual content of input_ndarray doesn't matter. The processor
  # only uses the type and geometry of the array for further processing.
  ignores_input_data = False

  def output_type(self, input_type: Union[np.uint8, np.uint64, np.float32]):
    """Returns Numpy output type of self.process for given input_type.

    Args:
      input_type: A Numpy type, should be one of np.uint8, np.uint64,
        np.float32.
    """
    return input_type

  @property
  def output_num(self) -> OutputNums:
    """Whether self.process produces single output or multiple per input."""
    return OutputNums.SINGLE

  @property
  def name_parts(self) -> Tuple[str]:
    """Returns Tuple[str] to be used in naming jobs, outputs, etc.

    Often useful to include both the name of the processor as well as relevant
    parameters.  The elements are generally joined with '_' or '-' depending on
    the context.
    """
    return type(self).__name__,

  def pixelsize(self, input_psize: array.ArrayLike3d) -> ImmutableArray:
    return ImmutableArray(input_psize)

  def num_channels(self, input_channels: int) -> int:
    return input_channels

  def process(
      self, subvol: subvolume.Subvolume
  ) -> Union[subvolume.Subvolume, list[subvolume.Subvolume]]:
    """Processes the input subvolume.

    Args:
      subvol: Subvolume to process.

    Returns:
      The processed subvolume. If self.context is > 0, it is expected that the
      returned subvolume will be smaller than the input by the context amount.
    """
    raise NotImplementedError

  def subvolume_size(self) -> Optional[TupleOrSuggestedXyz]:
    """Returns the XYZ subvolume size required by self.process.

    Some processors (e.g. TF inference models) may require specific input size.
    If the input size is just a suggestion, should return SuggestedXyz rather
    than raw tuple.  If there is no suggested input size, return None.
    """
    return None

  def context(self) -> Tuple[TupleOrSuggestedXyz, TupleOrSuggestedXyz]:
    """Returns XYZ front/back context needed for processing.

    It is expected that the return from self.process will be smaller than the
    input by this amount in front and back.
    """
    return SuggestedXyz(0, 0, 0), SuggestedXyz(0, 0, 0)

  def overlap(self) -> TupleOrSuggestedXyz:
    """Keep the type of context and sum front and back context."""
    f, b = self.context()
    overlap = f[0] + b[0], f[1] + b[1], f[2] + b[2]
    if isinstance(f, SuggestedXyz) and isinstance(b, SuggestedXyz):
      return SuggestedXyz(*overlap)
    return overlap

  def set_effective_subvol_and_overlap(self, subvol_size: array.ArrayLike3d,
                                       overlap: array.ArrayLike3d):
    """Assign the effective subvolume and overlap."""
    self._subvol_size = array.ImmutableArray(subvol_size)
    self._overlap = array.ImmutableArray(overlap)
    if np.all(self.overlap() == self._overlap):
      self._context = self.context()  # type: ignore
    else:
      pre = self._overlap // 2
      post = self._overlap - pre
      self._context = pre, post  # type: ignore

  def _context_for_box(
      self, box: bounding_box.BoundingBoxBase) -> Tuple[np.ndarray, np.ndarray]:
    front, back = self._context
    front = np.array(front)
    back = np.array(back)
    if not self.crop_at_borders:
      front *= ~box.is_border_start
      back *= ~box.is_border_end

    return front, back

  def expected_output_box(
      self, box: bounding_box.BoundingBoxBase) -> bounding_box.BoundingBoxBase:
    """Returns the adjusted bounding box after process() is called.

    Args:
        box: Size of the input subvolume passed to process()

    Returns:
        Bounding box for the output volume.
    """
    return box

  def crop_box(
      self, box: bounding_box.BoundingBoxBase) -> bounding_box.BoundingBoxBase:
    """Crop box front/back by self.context.

    Args:
      box: BoundingBox to crop.

    Returns:
      Copy of box with bounds reduced by front/back amount given by
      self.context.
    """
    front, back = self._context_for_box(box)
    return box.adjusted_by(start=front, end=-back)

  def crop_box_and_data(
      self,
      box: bounding_box.BoundingBoxBase,
      # TODO(timblakely): Strongly type this as ArrayCZYX
      data: np.ndarray
  ) -> Subvolume:
    """Crop data front/back by self.context.

    Args:
      box: bounding box corresponding to the data array
      data: 4d Numpy array with dimensions channels, Z, Y, X.

    Returns:
      View of data cropped by front/back amount given by self.context.
    """
    cropped_box = self.crop_box(box)
    front, back = self._context_for_box(box)
    fx, fy, fz = front
    bx, by, bz = np.array(data.shape[:0:-1]) - back
    return Subvolume(data[:, fz:bz, fy:by, fx:bx], cropped_box)


def get_processor(config: SubvolumeProcessorConfig) -> SubvolumeProcessor:
  name = config.name
  package = importlib.import_module(config.module_search_path)
  if not hasattr(package, name):
    raise ValueError(f'No processor named {name} in package {package}')
  processor = getattr(package, name)
  args = {} if not config.args else config.args
  return processor(**args)
