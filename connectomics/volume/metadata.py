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
"""Metadata for volumetric data."""

import dataclasses
import pathlib
from typing import Sequence

from connectomics.common import bounding_box
from connectomics.common import file
import dataclasses_json


@dataclasses_json.dataclass_json
@dataclasses.dataclass(frozen=True)
class VolumeMetadata:
  """Metadata associated with a Volume."""
  # Volume size in voxels. XYZ order.
  volume_size: tuple[int, int, int]
  # Pixel size in nm. XYZ order.
  pixel_size: tuple[float, float, float]
  bounding_boxes: list[bounding_box.BoundingBox]
  # TODO(timblakely): In the event we want to enforce the assumption that volumes
  # are XYZC (i.e. processing happens differently for spatial and channel axes),
  # add num_channels to this class to record any changes in channel counts.

  def scale(
      self, scale_factors: float | Sequence[float]
  ) -> 'VolumeMetadata':
    """Scales the volume metadata by the given scale factors.
    
    `scale_factors` must be a single float that will be applied multiplicatively
    to the volume size and pixel size, or a 3-element sequence of floats that
    will be applied to XYZ dimensions respectively.
    
    Args:
      scale_factors: The scale factors to apply.
    Returns:
      A new VolumeMetadata with the scaled values.
    """
    if isinstance(scale_factors, float) or isinstance(scale_factors, int):
      scale_factors = [scale_factors] * 3
    if len(scale_factors) != 3:
      raise ValueError('scale_factors must be a 3-element sequence.')
    return VolumeMetadata(
        volume_size=tuple(
            int(x * scale) for x, scale in zip(self.volume_size, scale_factors)
        ),
        pixel_size=tuple(
            x / scale for x, scale in zip(self.pixel_size, scale_factors)
        ),
        bounding_boxes=[
            bbox.scale(scale_factors) for bbox in self.bounding_boxes
        ],
    )

  def scale_xy(self, factor: float) -> 'VolumeMetadata':
    return self.scale([factor, factor, 1.0])


class Volume:
  path: pathlib.Path
  meta: VolumeMetadata

  def __init__(self, path: file.PathLike, meta: VolumeMetadata):
    self.path = pathlib.Path(path)
    self.meta = meta

  def save_metadata(self, kvdriver: str = 'file'):
    file.save_dataclass_json(
        self.meta,
        self.path.parent / f'{self.path.stem}.metadata.json',
        kvdriver=kvdriver,
    )
