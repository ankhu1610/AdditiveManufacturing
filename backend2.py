# backend.py

import os
import random
import numpy as np
import trimesh
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def make_interlock_hybrid(center, axis='x',
                          cyl_radius=0.4, cyl_height=0.6,
                          sphere_radius=0.5,
                          socket=False, tolerance=1.05,
                          flip_dir=False):
    """
    Creates a hybrid interlock: a short cylinder base + dome sphere.
    Embedded inside piece (inward).
    """
    cyl = trimesh.creation.cylinder(radius=cyl_radius,
                                    height=cyl_height,
                                    sections=24)
    cyl.apply_translation([0, 0, cyl_height / 2.0])

    sphere = trimesh.creation.icosphere(subdivisions=2,
                                        radius=sphere_radius)
    sphere.apply_translation([0, 0, cyl_height])

    try:
        hybrid = trimesh.boolean.union([cyl, sphere])
    except Exception:
        # Fallback: simple concatenation if boolean backend fails
        hybrid = trimesh.util.concatenate([cyl, sphere])

    if socket:
        hybrid.apply_scale(tolerance)

    # Orient along axis
    if axis == 'x':
        hybrid.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
        )
    elif axis == 'y':
        hybrid.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
        )

    # Push inward
    direction = -1 if not flip_dir else 1
    offset = cyl_height * 0.8 * direction
    if axis == 'x':
        hybrid.apply_translation([offset, 0, 0])
    elif axis == 'y':
        hybrid.apply_translation([0, offset, 0])
    elif axis == 'z':
        hybrid.apply_translation([0, 0, offset])

    # Move to target center in world coordinates
    hybrid.apply_translation(center)
    return hybrid


def generate_puzzle_from_stl(
        input_stl_path: str,
        divisions=(2, 2, 2),          # (nx, ny, nz)
        locks_per_face: int = 3,
        cyl_radius: float = 0.3,
        cyl_height: float = 0.5,
        sphere_radius: float = 0.4,
        socket_tolerance: float = 1.06,
        seed: int = 42,
        output_dir: str = "printable_puzzle"
):
    """
    Main pipeline:
    - Load and clean STL.
    - Cut into grid-based volumes.
    - Add hybrid interlocks.
    - Export puzzle pieces to STL.
    - Render multi-angle PNG previews.

    Returns:
        dict with:
            - 'piece_paths': list of STL file paths
            - 'view_image_paths': list of PNG file paths
            - 'mesh_info': mesh metadata
    """
    os.makedirs(output_dir, exist_ok=True)

    # ---- Step 0: Load mesh and clean ----
    mesh = trimesh.load_mesh(input_stl_path)
    mesh.remove_duplicate_faces()
    mesh.remove_degenerate_faces()
    try:
        mesh.fill_holes()
    except Exception:
        # Not fatal if hole fill fails
        pass
    mesh.process(validate=True)

    filled_mesh_file = os.path.join(output_dir, "input_filled.stl")
    mesh.export(filled_mesh_file)

    # ---- Step 1: Define grid cuts ----
    bounds = mesh.bounds
    x_min, y_min, z_min = bounds[0]
    x_max, y_max, z_max = bounds[1]

    nx, ny, nz = map(int, divisions)

    x_cuts = np.linspace(x_min, x_max, nx + 1)
    y_cuts = np.linspace(y_min, y_max, ny + 1)
    z_cuts = np.linspace(z_min, z_max, nz + 1)

    # Deterministic placement for reproducibility
    random.seed(seed)
    np.random.seed(seed)

    # ---- Step 3: Generate puzzle pieces with embedded interlocks ----
    piece_meshes = []
    piece_paths = []
    piece_count = 0

    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                x0, x1 = x_cuts[i], x_cuts[i + 1]
                y0, y1 = y_cuts[j], y_cuts[j + 1]
                z0, z1 = z_cuts[k], z_cuts[k + 1]

                cube = trimesh.creation.box(
                    extents=[x1 - x0, y1 - y0, z1 - z0]
                )
                cube.apply_translation(
                    [(x1 + x0) / 2, (y1 + y0) / 2, (z1 + z0) / 2]
                )

                try:
                    submesh = mesh.intersection(cube)
                    if submesh.is_empty:
                        continue
                except Exception as e:
                    print(f"Skipping piece ({i},{j},{k}) due to boolean error: {e}")
                    continue

                # --- X face interlocks ---
                if i < nx - 1:
                    face_x = x1
                    for n in range(locks_per_face):
                        cy = random.uniform(y0 + 0.2 * (y1 - y0),
                                            y1 - 0.2 * (y1 - y0))
                        cz = random.uniform(z0 + 0.2 * (z1 - z0),
                                            z1 - 0.2 * (z1 - z0))
                        center = [face_x, cy, cz]
                        try:
                            if ((i + j + k) % 2 == 0) ^ (n % 2 == 1):
                                key = make_interlock_hybrid(
                                    center, axis='x',
                                    cyl_radius=cyl_radius,
                                    cyl_height=cyl_height,
                                    sphere_radius=sphere_radius,
                                    socket=False, flip_dir=False
                                )
                                submesh = trimesh.boolean.union([submesh, key])
                            else:
                                socket = make_interlock_hybrid(
                                    center, axis='x',
                                    cyl_radius=cyl_radius,
                                    cyl_height=cyl_height,
                                    sphere_radius=sphere_radius,
                                    socket=True,
                                    tolerance=socket_tolerance,
                                    flip_dir=True
                                )
                                submesh = trimesh.boolean.difference([submesh, socket])
                        except Exception as e:
                            print(f"X-interlock error for piece ({i},{j},{k}): {e}")

                # --- Y face interlocks ---
                if j < ny - 1:
                    face_y = y1
                    for n in range(locks_per_face):
                        cx = random.uniform(x0 + 0.2 * (x1 - x0),
                                            x1 - 0.2 * (x1 - x0))
                        cz = random.uniform(z0 + 0.2 * (z1 - z0),
                                            z1 - 0.2 * (z1 - z0))
                        center = [cx, face_y, cz]
                        try:
                            if ((i + j + k) % 2 == 0) ^ (n % 2 == 1):
                                key = make_interlock_hybrid(
                                    center, axis='y',
                                    cyl_radius=cyl_radius,
                                    cyl_height=cyl_height,
                                    sphere_radius=sphere_radius,
                                    socket=False, flip_dir=False
                                )
                                submesh = trimesh.boolean.union([submesh, key])
                            else:
                                socket = make_interlock_hybrid(
                                    center, axis='y',
                                    cyl_radius=cyl_radius,
                                    cyl_height=cyl_height,
                                    sphere_radius=sphere_radius,
                                    socket=True,
                                    tolerance=socket_tolerance,
                                    flip_dir=True
                                )
                                submesh = trimesh.boolean.difference([submesh, socket])
                        except Exception as e:
                            print(f"Y-interlock error for piece ({i},{j},{k}): {e}")

                # --- Z face interlocks ---
                if k < nz - 1:
                    face_z = z1
                    for n in range(locks_per_face):
                        cx = random.uniform(x0 + 0.2 * (x1 - x0),
                                            x1 - 0.2 * (x1 - x0))
                        cy = random.uniform(y0 + 0.2 * (y1 - y0),
                                            y1 - 0.2 * (y1 - y0))
                        center = [cx, cy, face_z]
                        try:
                            if ((i + j + k) % 2 == 0) ^ (n % 2 == 1):
                                key = make_interlock_hybrid(
                                    center, axis='z',
                                    cyl_radius=cyl_radius,
                                    cyl_height=cyl_height,
                                    sphere_radius=sphere_radius,
                                    socket=False, flip_dir=False
                                )
                                submesh = trimesh.boolean.union([submesh, key])
                            else:
                                socket = make_interlock_hybrid(
                                    center, axis='z',
                                    cyl_radius=cyl_radius,
                                    cyl_height=cyl_height,
                                    sphere_radius=sphere_radius,
                                    socket=True,
                                    tolerance=socket_tolerance,
                                    flip_dir=True
                                )
                                submesh = trimesh.boolean.difference([submesh, socket])
                        except Exception as e:
                            print(f"Z-interlock error for piece ({i},{j},{k}): {e}")

                # Export piece
                filename = os.path.join(output_dir,
                                        f"piece_{i}_{j}_{k}.stl")
                try:
                    submesh.export(filename)
                    piece_meshes.append(submesh)
                    piece_paths.append(filename)
                    piece_count += 1
                    print(f"Exported {filename}")
                except Exception as e:
                    print(f"Failed to export piece ({i},{j},{k}): {e}")

    print(f"\n✅ Exported {piece_count} puzzle pieces to folder '{output_dir}'")

    # ---- Step 4: Multi-angle 3D Visualization ----
    view_image_paths = []

    if len(piece_meshes) > 0:
        fig = plt.figure(figsize=(12, 9))
        ax = fig.add_subplot(111, projection='3d')

        colors = plt.cm.tab20(np.linspace(0, 1, max(1, len(piece_meshes))))

        for idx, submesh in enumerate(piece_meshes):
            try:
                faces = submesh.triangles
                color = colors[idx % len(colors)]
                ax.add_collection3d(
                    Poly3DCollection(
                        faces,
                        facecolors=color,
                        linewidths=0.02,
                        alpha=0.9
                    )
                )
            except Exception as e:
                print(f"Visualization warning for piece {idx}: {e}")

        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_zlim(z_min, z_max)
        ax.set_box_aspect([x_max - x_min,
                           y_max - y_min,
                           z_max - z_min])

        ax.set_xlabel('X Axis')
        ax.set_ylabel('Y Axis')
        ax.set_zlabel('Z Axis')
        ax.set_title('3D Puzzle Pieces Visualization (Embedded Hybrid Locks)',
                     fontsize=14)

        plt.tight_layout()

        view_angles = [
            (20, 30),
            (90, 0),
            (0, 0),
            (0, 90),
            (45, 45)
        ]

        for idx, (elev, azim) in enumerate(view_angles):
            ax.view_init(elev=elev, azim=azim)
            view_path = os.path.join(
                output_dir,
                f"puzzle_view_{idx + 1}_e{elev}_a{azim}.png"
            )
            plt.savefig(view_path, dpi=300, bbox_inches='tight')
            print(f"🖼️ Saved 3D puzzle view {idx + 1} → '{view_path}'")
            view_image_paths.append(view_path)

        plt.close(fig)
        print(f"\n✅ All {len(view_angles)} views saved successfully in '{output_dir}'")

    mesh_info = {
        "bounds": bounds,
        "watertight": bool(mesh.is_watertight),
        "filled_mesh_file": filled_mesh_file,
        "piece_count": piece_count
    }

    return {
        "piece_paths": piece_paths,
        "view_image_paths": view_image_paths,
        "mesh_info": mesh_info
    }
