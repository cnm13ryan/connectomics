# coding=utf-8
# Copyright 2023 The Google Research Authors.
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
"""Tests for rag."""

from absl.testing import absltest
from connectomics.segmentation import rag
import networkx as nx
from scipy import spatial


class RagTest(absltest.TestCase):

  def test_from_set_points(self):
    # Each segment is associated with just a single 3d point.
    kdts = {
        1: spatial.cKDTree([(1, 1, 1)]),
        2: spatial.cKDTree([(2, 1, 1)]),
        3: spatial.cKDTree([(3, 1, 1)]),
    }
    g = rag.from_set(kdts)
    self.assertTrue(nx.utils.edges_equal(g.edges(), ((1, 2), (2, 3))))

  def test_from_set_skeletons(self):
    # Each segment is associated with a short skeleton fragment.
    skels = {
        1: nx.Graph([(0, 1), (1, 2), (2, 3)]),
        2: nx.Graph([(0, 1), (1, 2), (2, 3)]),
        3: nx.Graph([(0, 1), (1, 2)]),
    }

    # Add spatial coordinates for all skeleton nodes.
    skels[1].nodes[0]['position'] = (0, 1, 0)
    skels[1].nodes[1]['position'] = (0, 2, 0)
    skels[1].nodes[2]['position'] = (0, 3, 0)
    skels[1].nodes[3]['position'] = (0, 4, 0)  # *

    skels[2].nodes[0]['position'] = (0, 5, 1)  # *
    skels[2].nodes[1]['position'] = (0, 5, 2)
    skels[2].nodes[2]['position'] = (0, 5, 3)
    skels[2].nodes[3]['position'] = (0, 5, 4)  # %

    skels[3].nodes[0]['position'] = (0, 8, 6)
    skels[3].nodes[1]['position'] = (0, 7, 5)
    skels[3].nodes[2]['position'] = (0, 6, 4)  # %

    # Convert skeletons to k-d trees and build RAG.
    kdts = {
        k: spatial.cKDTree([n['position'] for _, n in v.nodes(data=True)])
        for k, v in skels.items()
    }
    g = rag.from_set(kdts)
    self.assertTrue(nx.utils.edges_equal(g.edges(), ((1, 2), (2, 3))))

    # Verify which specific points got connected (marked with * and %
    # in the comments above).
    self.assertEqual(g.edges[1, 2]['idx1'], 3)
    self.assertEqual(g.edges[1, 2]['idx2'], 0)

    self.assertEqual(g.edges[2, 3]['idx1'], 3)
    self.assertEqual(g.edges[2, 3]['idx2'], 2)


if __name__ == '__main__':
  absltest.main()
