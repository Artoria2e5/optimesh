# -*- coding: utf-8 -*-
#
import fastfunc
import numpy

from .ghosted_mesh import GhostedMesh
from .helpers import jac_uniform

from ..helpers import runner


def quasi_newton_uniform_blocks(points, cells, *args, **kwargs):
    """Lloyd's algorithm can be though of a diagonal-only Hessian; this method
    incorporates the diagonal blocks, too.
    """

    def get_new_points(mesh):
        # TODO need copy?
        x = mesh.node_coords.copy()
        x += update(mesh)
        return x[mesh.is_interior_node]

    ghosted_mesh = GhostedMesh(points, cells)

    runner(
        get_new_points,
        ghosted_mesh.mesh,
        *args,
        **kwargs,
        straighten_out=lambda mesh: ghosted_mesh.straighten_out(),
        # get_stats_mesh=lambda mesh: ghosted_mesh.get_stats_mesh(),
    )

    mesh = ghosted_mesh.get_stats_mesh()
    # mesh = ghosted_mesh.mesh
    return mesh.node_coords, mesh.cells["nodes"]


def update(mesh):
    X = mesh.node_coords

    # TODO remove this assertion and test
    # flat mesh
    assert X.shape[1] == 2

    # Collect the diagonal blocks.
    diagonal_blocks = numpy.zeros((X.shape[0], 2, 2))

    # First the Lloyd part.
    diagonal_blocks[:, 0, 0] += 2 * mesh.control_volumes
    diagonal_blocks[:, 1, 1] += 2 * mesh.control_volumes

    ei_outer_ei = numpy.einsum(
        "ijk, ijl->ijkl", mesh.half_edge_coords, mesh.half_edge_coords
    )

    # Without adding the control volumes above, the update would be
    # ```
    # m = 0.5 * ce * (numpy.eye(2) * numpy.dot(ei, ei) - ei_outer_ei)
    # ```
    # instead of
    # ```
    # m = -0.5 * ce * ei_outer_ei
    # ```
    # This makes clear why the diagonal blocks are always positive definite if the mesh
    # is Delaunay.
    M = -0.5 * ei_outer_ei * mesh.ce_ratios[..., None, None]

    fastfunc.add.at(diagonal_blocks, mesh.idx_hierarchy[0], M)
    fastfunc.add.at(diagonal_blocks, mesh.idx_hierarchy[1], M)

    rhs = -jac_uniform(mesh).reshape(-1, 2)

    # set the boundary blocks to the identity
    diagonal_blocks[mesh.is_boundary_node] = 0.0
    diagonal_blocks[mesh.is_boundary_node, 0, 0] = 1.0
    diagonal_blocks[mesh.is_boundary_node, 1, 1] = 1.0
    rhs[mesh.is_boundary_node] = 0.0

    return numpy.linalg.solve(diagonal_blocks, rhs)