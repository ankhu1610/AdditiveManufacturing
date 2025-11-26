# app.py

import os
import io
import tempfile
import zipfile

import streamlit as st

from backend import generate_puzzle_from_stl


st.set_page_config(
    page_title="3D Puzzle Generator – Hybrid Locks",
    layout="wide"
)

st.title("🧩 3D Printable Puzzle Generator")
st.markdown(
    "Upload an STL, choose how many cuts you want, and let the backend "
    "carve it into interlocking puzzle pieces with hybrid cylinder+dome keys."
)

# ---------- File upload ----------
uploaded_file = st.file_uploader("Upload STL file", type=["stl"])

st.sidebar.header("Grid & Interlock Parameters")

# Grid divisions
col_div = st.sidebar.columns(3)
nx = col_div[0].number_input("Divisions X", min_value=1, max_value=10, value=2, step=1)
ny = col_div[1].number_input("Divisions Y", min_value=1, max_value=10, value=2, step=1)
nz = col_div[2].number_input("Divisions Z", min_value=1, max_value=10, value=2, step=1)

# Interlock parameters
locks_per_face = st.sidebar.slider("Locks per face", min_value=1, max_value=6, value=3)

cyl_radius = st.sidebar.number_input(
    "Cylinder radius", min_value=0.1, max_value=10.0, value=0.3, step=0.1
)
cyl_height = st.sidebar.number_input(
    "Cylinder height", min_value=0.1, max_value=20.0, value=0.5, step=0.1
)
sphere_radius = st.sidebar.number_input(
    "Dome (sphere) radius", min_value=0.1, max_value=10.0, value=0.4, step=0.1
)
socket_tolerance = st.sidebar.number_input(
    "Socket tolerance scale", min_value=1.0, max_value=1.2, value=1.06, step=0.01
)

seed = st.sidebar.number_input("Random seed", min_value=0, max_value=99999, value=42)

generate_btn = st.button("Generate Puzzle Pieces")

if generate_btn:
    if uploaded_file is None:
        st.error("Please upload an STL file first.")
    else:
        # ---------- Save uploaded STL to a temp folder ----------
        tmp_dir = tempfile.mkdtemp(prefix="puzzle_")
        input_path = os.path.join(tmp_dir, "input.stl")

        with open(input_path, "wb") as f:
            f.write(uploaded_file.read())

        st.info("Processing mesh and generating puzzle pieces…")

        # ---------- Call backend ----------
        with st.spinner("Crunching geometry and boolean operations…"):
            result = generate_puzzle_from_stl(
                input_stl_path=input_path,
                divisions=(nx, ny, nz),
                locks_per_face=locks_per_face,
                cyl_radius=cyl_radius,
                cyl_height=cyl_height,
                sphere_radius=sphere_radius,
                socket_tolerance=socket_tolerance,
                seed=int(seed),
                output_dir=os.path.join(tmp_dir, "printable_puzzle")
            )

        mesh_info = result["mesh_info"]
        piece_paths = result["piece_paths"]
        view_paths = result["view_image_paths"]

        st.success(
            f"Done! Exported {mesh_info['piece_count']} pieces. "
            f"Watertight: {mesh_info['watertight']} | "
            f"Bounds: {mesh_info['bounds']}"
        )

        # ---------- Download: cleaned mesh ----------
        st.subheader("Cleaned Mesh (with holes filled)")
        try:
            with open(mesh_info["filled_mesh_file"], "rb") as f:
                st.download_button(
                    "Download cleaned STL",
                    data=f,
                    file_name="input_filled.stl"
                )
        except Exception:
            st.warning("Could not expose cleaned mesh file for download.")

        # ---------- Download: all puzzle pieces as ZIP ----------
        if piece_paths:
            st.subheader("Puzzle Pieces")

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zipf:
                for p in piece_paths:
                    zipf.write(p, arcname=os.path.basename(p))
            zip_buf.seek(0)

            st.download_button(
                "⬇️ Download all puzzle pieces (ZIP)",
                data=zip_buf,
                file_name="puzzle_pieces.zip"
            )
        else:
            st.warning("No pieces were generated — check your parameters or STL integrity.")

        # ---------- Preview images ----------
        if view_paths:
            st.subheader("3D Views of Puzzle Assembly")
            cols = st.columns(2)
            for idx, img_path in enumerate(view_paths):
                col = cols[idx % 2]
                col.image(img_path, caption=os.path.basename(img_path), use_container_width=True)
        else:
            st.info("No preview images generated – something may have failed in visualization.")

st.markdown("---")
st.caption(
    "Note: Boolean operations in Trimesh can be sensitive to mesh quality and "
    "backend availability (e.g., scad/meshboolean). If pieces fail, try a "
    "simpler model, fewer divisions, or repair your STL in a mesh tool first."
)
