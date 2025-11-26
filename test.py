import trimesh
import numpy as np
import os, random
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# -------------------------------
# Step 0: Load mesh and clean
# -------------------------------
mesh = trimesh.load_mesh("input.stl")
mesh.remove_duplicate_faces()
mesh.remove_degenerate_faces()
mesh.fill_holes()
mesh.process(validate=True)
print(f"Mesh loaded and cleaned: {mesh.bounds}, watertight: {mesh.is_watertight}")

filled_mesh_file = "input_filled.stl"
mesh.export(filled_mesh_file)
print(f"✅ Exported hole-filled mesh as '{filled_mesh_file}'")

# -------------------------------
# Step 1: Define grid cuts (Dynamic divisions)
# -------------------------------
bounds = mesh.bounds
x_min, y_min, z_min = bounds[0]
x_max, y_max, z_max = bounds[1]

num_divisions = tuple(map(int, input("Enter divisions along X Y Z (e.g., 2 2 2): ").split()))
x_cuts = np.linspace(x_min, x_max, num_divisions[0] + 1)
y_cuts = np.linspace(y_min, y_max, num_divisions[1] + 1)
z_cuts = np.linspace(z_min, z_max, num_divisions[2] + 1)

output_dir = "printable_puzzle"
os.makedirs(output_dir, exist_ok=True)

random.seed(42)  # deterministic placement for reproducibility
# -------------------------------
# Step 2: Enhanced Hybrid Interlock (cylinder + dome) with better fitting
# -------------------------------
def make_interlock_hybrid(center, axis='x', cyl_radius=0.4, cyl_height=0.6, sphere_radius=0.5, 
                          socket=False, tolerance=1.03, flip_dir=False, interlock_type='standard'):
    """
    Enhanced hybrid interlock with multiple design options for better fitting.
    Options: 'standard', 'tapered', 'double_dome', 'keyhole'
    """
    # Base parameters with better proportions
    base_cyl_radius = cyl_radius
    base_cyl_height = cyl_height * 0.8  # Shorter cylinder for better stability
    dome_sphere_radius = sphere_radius * 0.9  # Slightly smaller dome
    
    if interlock_type == 'tapered':
        # Tapered cylinder + dome for easier insertion
        cyl = trimesh.creation.cylinder(radius=base_cyl_radius, height=base_cyl_height, sections=32)
        # Create tapered top
        taper = trimesh.creation.cone(radius=base_cyl_radius, height=base_cyl_height * 0.3, sections=24)
        taper.apply_translation([0, 0, base_cyl_height])
        sphere = trimesh.creation.icosphere(subdivisions=2, radius=dome_sphere_radius * 0.8)
        sphere.apply_translation([0, 0, base_cyl_height + base_cyl_height * 0.3])
        parts = [cyl, taper, sphere]
        
    elif interlock_type == 'double_dome':
        # Cylinder with dome on both ends
        cyl = trimesh.creation.cylinder(radius=base_cyl_radius, height=base_cyl_height, sections=32)
        cyl.apply_translation([0, 0, base_cyl_height / 2.0])
        
        top_sphere = trimesh.creation.icosphere(subdivisions=2, radius=dome_sphere_radius)
        top_sphere.apply_translation([0, 0, base_cyl_height])
        
        bottom_sphere = trimesh.creation.icosphere(subdivisions=2, radius=dome_sphere_radius * 0.7)
        bottom_sphere.apply_translation([0, 0, 0])
        
        parts = [cyl, top_sphere, bottom_sphere]
        
    elif interlock_type == 'keyhole':
        # Cylinder with elongated dome for keyhole effect
        cyl = trimesh.creation.cylinder(radius=base_cyl_radius, height=base_cyl_height, sections=32)
        cyl.apply_translation([0, 0, base_cyl_height / 2.0])
        
        # Ellipsoid instead of sphere for keyhole shape
        ellipsoid = trimesh.creation.icosphere(subdivisions=2, radius=dome_sphere_radius)
        # Scale to make elliptical
        ellipsoid.apply_scale([1.0, 1.0, 1.3])
        ellipsoid.apply_translation([0, 0, base_cyl_height])
        
        parts = [cyl, ellipsoid]
        
    else:  # 'standard' - improved version
        # Standard cylinder + dome with better proportions
        cyl = trimesh.creation.cylinder(radius=base_cyl_radius, height=base_cyl_height, sections=32)
        cyl.apply_translation([0, 0, base_cyl_height / 2.0])
        
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=dome_sphere_radius)  # More subdivisions for smoother dome
        sphere.apply_translation([0, 0, base_cyl_height])
        
        parts = [cyl, sphere]

    # Combine parts
    try:
        hybrid = trimesh.boolean.union(parts)
    except Exception:
        hybrid = trimesh.util.concatenate(parts)

    # Apply socket tolerance with careful scaling
    if socket:
        # Scale only in the insertion direction for better fit
        scale_matrix = np.eye(4)
        if axis == 'x':
            scale_matrix[0, 0] = tolerance
            scale_matrix[1, 1] = tolerance * 1.02  # Slightly more tolerance in other directions
            scale_matrix[2, 2] = tolerance * 1.02
        elif axis == 'y':
            scale_matrix[0, 0] = tolerance * 1.02
            scale_matrix[1, 1] = tolerance
            scale_matrix[2, 2] = tolerance * 1.02
        else:  # z-axis
            scale_matrix[0, 0] = tolerance * 1.02
            scale_matrix[1, 1] = tolerance * 1.02
            scale_matrix[2, 2] = tolerance
        hybrid.apply_transform(scale_matrix)

    # Orient along axis with proper rotation
    if axis == 'x':
        hybrid.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    elif axis == 'y':
        hybrid.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    # z-axis remains default orientation

    # Calculate smart offset based on interlock type
    if interlock_type == 'double_dome':
        offset_distance = base_cyl_height * 0.6
    elif interlock_type == 'keyhole':
        offset_distance = base_cyl_height * 0.7
    else:
        offset_distance = base_cyl_height * 0.8

    # Push inward/outward with calculated offset
    direction = -1 if not flip_dir else 1
    offset = offset_distance * direction
    
    if axis == 'x':
        hybrid.apply_translation([offset, 0, 0])
    elif axis == 'y':
        hybrid.apply_translation([0, offset, 0])
    elif axis == 'z':
        hybrid.apply_translation([0, 0, offset])

    hybrid.apply_translation(center)
    return hybrid

# -------------------------------
# Step 3: Enhanced puzzle piece generation with smart interlock placement
# -------------------------------
piece_meshes = []
piece_count = 0

# Enhanced parameters
locks_per_face = 2  # Reduced for cleaner design but better quality
cyl_radius = 0.35
cyl_height = 0.5
sphere_radius = 0.45
socket_tolerance = 1.04  # Reduced tolerance for tighter fit

# Define interlock types for variety
interlock_types = ['standard', 'tapered', 'double_dome', 'keyhole']

for i in range(num_divisions[0]):
    for j in range(num_divisions[1]):
        for k in range(num_divisions[2]):
            x0, x1 = x_cuts[i], x_cuts[i+1]
            y0, y1 = y_cuts[j], y_cuts[j+1]
            z0, z1 = z_cuts[k], z_cuts[k+1]

            cube = trimesh.creation.box(extents=[x1-x0, y1-y0, z1-z0])
            cube.apply_translation([(x1+x0)/2, (y1+y0)/2, (z1+z0)/2])

            try:
                submesh = mesh.intersection(cube)
                if submesh.is_empty:
                    continue
            except Exception as e:
                print(f"Skipping piece ({i},{j},{k}) due to boolean error: {e}")
                continue

            # Smart interlock type selection based on position
            base_type_idx = (i + j * 2 + k * 3) % len(interlock_types)
            interlock_type = interlock_types[base_type_idx]

            # --- X face interlocks ---
            if i < num_divisions[0]-1:
                face_x = x1
                for n in range(locks_per_face):
                    # More strategic placement avoiding edges
                    edge_margin = 0.25
                    cy = random.uniform(y0 + edge_margin*(y1-y0), y1 - edge_margin*(y1-y0))
                    cz = random.uniform(z0 + edge_margin*(z1-z0), z1 - edge_margin*(z1-z0))
                    center = [face_x, cy, cz]
                    
                    # Alternate key/socket pattern with position-based variation
                    is_key = ((i+j+k) % 2 == 0) ^ (n % 2 == 1)
                    
                    try:
                        if is_key:
                            key = make_interlock_hybrid(center, axis='x', cyl_radius=cyl_radius, 
                                                        cyl_height=cyl_height, sphere_radius=sphere_radius, 
                                                        socket=False, flip_dir=False, interlock_type=interlock_type)
                            submesh = trimesh.boolean.union([submesh, key])
                        else:
                            socket = make_interlock_hybrid(center, axis='x', cyl_radius=cyl_radius, 
                                                           cyl_height=cyl_height, sphere_radius=sphere_radius, 
                                                           socket=True, tolerance=socket_tolerance, 
                                                           flip_dir=True, interlock_type=interlock_type)
                            submesh = trimesh.boolean.difference([submesh, socket])
                    except Exception as e:
                        print(f"X-interlock error for piece ({i},{j},{k}): {e}")

            # --- Y face interlocks ---
            if j < num_divisions[1]-1:
                face_y = y1
                for n in range(locks_per_face):
                    edge_margin = 0.25
                    cx = random.uniform(x0 + edge_margin*(x1-x0), x1 - edge_margin*(x1-x0))
                    cz = random.uniform(z0 + edge_margin*(z1-z0), z1 - edge_margin*(z1-z0))
                    center = [cx, face_y, cz]
                    
                    is_key = ((i+j+k) % 2 == 0) ^ (n % 2 == 1)
                    
                    try:
                        if is_key:
                            key = make_interlock_hybrid(center, axis='y', cyl_radius=cyl_radius, 
                                                        cyl_height=cyl_height, sphere_radius=sphere_radius, 
                                                        socket=False, flip_dir=False, interlock_type=interlock_type)
                            submesh = trimesh.boolean.union([submesh, key])
                        else:
                            socket = make_interlock_hybrid(center, axis='y', cyl_radius=cyl_radius, 
                                                           cyl_height=cyl_height, sphere_radius=sphere_radius, 
                                                           socket=True, tolerance=socket_tolerance, 
                                                           flip_dir=True, interlock_type=interlock_type)
                            submesh = trimesh.boolean.difference([submesh, socket])
                    except Exception as e:
                        print(f"Y-interlock error for piece ({i},{j},{k}): {e}")

            # --- Z face interlocks ---
            if k < num_divisions[2]-1:
                face_z = z1
                for n in range(locks_per_face):
                    edge_margin = 0.25
                    cx = random.uniform(x0 + edge_margin*(x1-x0), x1 - edge_margin*(x1-x0))
                    cy = random.uniform(y0 + edge_margin*(y1-y0), y1 - edge_margin*(y1-y0))
                    center = [cx, cy, face_z]
                    
                    is_key = ((i+j+k) % 2 == 0) ^ (n % 2 == 1)
                    
                    try:
                        if is_key:
                            key = make_interlock_hybrid(center, axis='z', cyl_radius=cyl_radius, 
                                                        cyl_height=cyl_height, sphere_radius=sphere_radius, 
                                                        socket=False, flip_dir=False, interlock_type=interlock_type)
                            submesh = trimesh.boolean.union([submesh, key])
                        else:
                            socket = make_interlock_hybrid(center, axis='z', cyl_radius=cyl_radius, 
                                                           cyl_height=cyl_height, sphere_radius=sphere_radius, 
                                                           socket=True, tolerance=socket_tolerance, 
                                                           flip_dir=True, interlock_type=interlock_type)
                            submesh = trimesh.boolean.difference([submesh, socket])
                    except Exception as e:
                        print(f"Z-interlock error for piece ({i},{j},{k}): {e}")

            # Clean up the mesh before export
            try:
                submesh = submesh.process(validate=True)
                submesh.remove_degenerate_faces()
                submesh.remove_duplicate_faces()
            except Exception as e:
                print(f"Mesh cleanup warning for piece ({i},{j},{k}): {e}")

            # Export piece
            filename = os.path.join(output_dir, f"piece_{i}_{j}_{k}.stl")
            try:
                submesh.export(filename)
                piece_meshes.append(submesh)
                piece_count += 1
                print(f"Exported {filename} with {interlock_type} interlocks")
            except Exception as e:
                print(f"Failed to export piece ({i},{j},{k}): {e}")

# -------------------------------
# Step 4: Multi-angle 3D Visualization
# -------------------------------
fig = plt.figure(figsize=(12, 9))
ax = fig.add_subplot(111, projection='3d')

colors = plt.cm.tab20(np.linspace(0, 1, max(1, len(piece_meshes))))

for idx, submesh in enumerate(piece_meshes):
    try:
        faces = submesh.triangles
        color = colors[idx % len(colors)]
        ax.add_collection3d(Poly3DCollection(faces, facecolors=color, linewidths=0.02, alpha=0.9))
    except Exception as e:
        print(f"Visualization warning for piece {idx}: {e}")

ax.set_xlim(x_min, x_max)
ax.set_ylim(y_min, y_max)
ax.set_zlim(z_min, z_max)
ax.set_box_aspect([x_max - x_min, y_max - y_min, z_max - z_min])

ax.set_xlabel('X Axis')
ax.set_ylabel('Y Axis')
ax.set_zlabel('Z Axis')
ax.set_title('3D Puzzle Pieces Visualization (Embedded Hybrid Locks)', fontsize=14)

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
    view_path = os.path.join(output_dir, f"puzzle_view_{idx+1}_e{elev}_a{azim}.png")
    plt.savefig(view_path, dpi=300, bbox_inches='tight')
    print(f"🖼️ Saved 3D puzzle view {idx+1} → '{view_path}'")

plt.close(fig)
print(f"\n✅ All {len(view_angles)} views saved successfully in '{output_dir}'")
