# app.py

import os
import io
import time
import tempfile
import zipfile

import streamlit as st
import pandas as pd

from backend import generate_puzzle_from_stl

st.set_page_config(
    page_title="3D Puzzle Generator – Hybrid Locks",
    layout="wide"
)

# Custom CSS for better progress indicators
st.markdown("""
<style>
    .progress-container {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        background-color: #f9f9f9;
    }
    .step-complete {
        color: #00aa00;
        font-weight: bold;
    }
    .step-active {
        color: #0066cc;
        font-weight: bold;
    }
    .step-pending {
        color: #666666;
    }
    .progress-bar {
        height: 10px;
        background-color: #e0e0e0;
        border-radius: 5px;
        margin: 10px 0;
    }
    .progress-fill {
        height: 100%;
        background-color: #00aa00;
        border-radius: 5px;
        transition: width 0.3s ease;
    }
    .piece-status {
        font-family: monospace;
        font-size: 0.9em;
        background-color: #f0f0f0;
        padding: 2px 6px;
        border-radius: 3px;
        margin: 2px 0;
    }
    .success-box {
        border: 2px solid #00aa00;
        border-radius: 10px;
        padding: 20px;
        background-color: #f0fff0;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

st.title("🧩 3D Printable Puzzle Generator")
st.markdown(
    "Upload an STL, choose how many cuts you want, and let the backend "
    "carve it into interlocking puzzle pieces with hybrid cylinder+dome keys."
)

# Initialize session state
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'result' not in st.session_state:
    st.session_state.result = None
if 'progress_data' not in st.session_state:
    st.session_state.progress_data = {
        'current_step': 'Ready',
        'progress': 0,
        'completed_steps': [],
        'piece_status': [],
        'start_time': None
    }

# ---------- File upload ----------
uploaded_file = st.file_uploader("Upload STL file", type=["stl"])

st.sidebar.header("Grid & Interlock Parameters")

# Grid divisions
col_div = st.sidebar.columns(3)
nx = col_div[0].number_input("Divisions X", min_value=1, max_value=6, value=2, step=1)
ny = col_div[1].number_input("Divisions Y", min_value=1, max_value=6, value=2, step=1)
nz = col_div[2].number_input("Divisions Z", min_value=1, max_value=6, value=2, step=1)

# Interlock parameters
locks_per_face = st.sidebar.slider("Locks per face", min_value=1, max_value=4, value=2)

cyl_radius = st.sidebar.number_input(
    "Cylinder radius", min_value=0.1, max_value=5.0, value=0.3, step=0.1
)
cyl_height = st.sidebar.number_input(
    "Cylinder height", min_value=0.1, max_value=10.0, value=0.5, step=0.1
)
sphere_radius = st.sidebar.number_input(
    "Dome (sphere) radius", min_value=0.1, max_value=5.0, value=0.4, step=0.1
)
socket_tolerance = st.sidebar.number_input(
    "Socket tolerance scale", min_value=1.0, max_value=1.2, value=1.06, step=0.01
)

seed = st.sidebar.number_input("Random seed", min_value=0, max_value=99999, value=42)

# Progress display component
def display_progress():
    progress_data = st.session_state.progress_data
    
    # Progress bar
    st.markdown(f"**Overall Progress: {progress_data['progress']}%**")
    st.markdown(f"""
    <div class="progress-bar">
        <div class="progress-fill" style="width: {min(progress_data['progress'], 100)}%"></div>
    </div>
    """, unsafe_allow_html=True)
    
    # Current step
    if progress_data['current_step']:
        st.markdown(f"**Current Step:** <span class='step-active'>{progress_data['current_step']}</span>", 
                    unsafe_allow_html=True)
    
    # Elapsed time
    if progress_data['start_time']:
        elapsed = time.time() - progress_data['start_time']
        st.markdown(f"**Elapsed Time:** {elapsed:.1f} seconds")
    
    # Completed steps
    if progress_data['completed_steps']:
        with st.expander("✅ Completed Steps", expanded=True):
            for step in progress_data['completed_steps']:
                st.markdown(f"✓ {step}")
    
    # Piece status (if available)
    if progress_data['piece_status']:
        with st.expander("🔧 Piece Generation Status", expanded=True):
            for status in progress_data['piece_status'][-10:]:  # Show last 10
                st.markdown(f"<div class='piece-status'>{status}</div>", unsafe_allow_html=True)

# Progress callback function
def progress_callback(step, progress, piece_info=None):
    """Update progress in session state"""
    if step and step not in st.session_state.progress_data['completed_steps']:
        st.session_state.progress_data['completed_steps'].append(step)
        st.session_state.progress_data['current_step'] = step
    
    if progress is not None:
        st.session_state.progress_data['progress'] = progress
    
    if piece_info:
        st.session_state.progress_data['piece_status'].append(
            f"{time.strftime('%H:%M:%S')} - {piece_info}"
        )

# Enhanced processing WITHOUT threads
generate_btn = st.button("Generate Puzzle Pieces", 
                        disabled=st.session_state.processing,
                        type="primary")

if generate_btn and not st.session_state.processing:
    if uploaded_file is None:
        st.error("Please upload an STL file first.")
    else:
        st.session_state.processing = True
        st.session_state.result = None
        
        # Initialize progress data
        st.session_state.progress_data = {
            'current_step': 'Initializing...',
            'progress': 0,
            'completed_steps': [],
            'piece_status': [],
            'start_time': time.time()
        }
        
        # Create a progress placeholder
        progress_placeholder = st.empty()
        
        with progress_placeholder.container():
            st.info("🔄 Processing mesh and generating puzzle pieces…")
            display_progress()
        
        # Save uploaded STL to temp folder
        tmp_dir = tempfile.mkdtemp(prefix="puzzle_")
        input_path = os.path.join(tmp_dir, "input.stl")

        with open(input_path, "wb") as f:
            f.write(uploaded_file.getvalue())

        # Prepare parameters
        params = {
            'divisions': (nx, ny, nz),
            'locks_per_face': locks_per_face,
            'cyl_radius': cyl_radius,
            'cyl_height': cyl_height,
            'sphere_radius': sphere_radius,
            'socket_tolerance': socket_tolerance,
            'seed': int(seed),
            'output_dir': os.path.join(tmp_dir, "printable_puzzle")
        }

        try:
            # Call the backend function directly (no threading)
            result = generate_puzzle_from_stl(
                input_stl_path=input_path,
                divisions=params['divisions'],
                locks_per_face=params['locks_per_face'],
                cyl_radius=params['cyl_radius'],
                cyl_height=params['cyl_height'],
                sphere_radius=params['sphere_radius'],
                socket_tolerance=params['socket_tolerance'],
                seed=params['seed'],
                output_dir=params['output_dir'],
                progress_callback=progress_callback
            )
            
            st.session_state.result = result
            st.session_state.processing = False
            
            # Clear progress placeholder
            progress_placeholder.empty()
            
            # Show success message
            st.success("✅ Processing completed successfully!")
            
        except Exception as e:
            st.session_state.processing = False
            progress_placeholder.empty()
            st.error(f"❌ Processing failed: {str(e)}")
        
        st.rerun()

# Display progress if processing
if st.session_state.processing:
    # This will be handled in the button click above
    pass

# Display results when processing is complete
elif st.session_state.result is not None:
    result = st.session_state.result
    mesh_info = result["mesh_info"]
    piece_paths = result["piece_paths"]
    view_paths = result["view_image_paths"]

    # Success summary
    st.markdown(f"""
    <div class="success-box">
        <h3>✅ Processing Complete!</h3>
        <p><strong>Pieces Generated:</strong> {mesh_info['piece_count']}</p>
        <p><strong>Success Rate:</strong> {mesh_info.get('success_rate', 'N/A')}</p>
        <p><strong>Watertight:</strong> {mesh_info['watertight']}</p>
        <p><strong>Total Time:</strong> {time.time() - st.session_state.progress_data['start_time']:.1f} seconds</p>
    </div>
    """, unsafe_allow_html=True)

    # ---------- Download Section ----------
    st.subheader("📁 Download Results")
    
    # Create two columns for download buttons
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Cleaned Mesh (with holes filled)**")
        try:
            if os.path.exists(mesh_info["filled_mesh_file"]):
                with open(mesh_info["filled_mesh_file"], "rb") as f:
                    st.download_button(
                        "📥 Download cleaned STL",
                        data=f.read(),
                        file_name="input_filled.stl",
                        icon="📦",
                        use_container_width=True,
                        key="download_cleaned"
                    )
            else:
                st.warning("Cleaned mesh file not found")
        except Exception as e:
            st.warning(f"Could not load cleaned mesh: {e}")

    with col2:
        if piece_paths and len(piece_paths) > 0:
            st.write(f"**Puzzle Pieces ({len(piece_paths)} files)**")
            
            # Create ZIP file
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zipf:
                for p in piece_paths:
                    if os.path.exists(p):
                        zipf.write(p, arcname=os.path.basename(p))
                    else:
                        st.warning(f"File not found: {p}")
            
            if zip_buf.tell() > 0:  # Check if ZIP has content
                zip_buf.seek(0)
                st.download_button(
                    "📦 Download all puzzle pieces (ZIP)",
                    data=zip_buf.getvalue(),
                    file_name="puzzle_pieces.zip",
                    icon="📦",
                    use_container_width=True,
                    key="download_zip"
                )
            else:
                st.error("No puzzle pieces were generated successfully")
        else:
            st.error("❌ No puzzle pieces were generated. Please check your STL file and parameters.")

    # ---------- Preview images ----------
    if view_paths and len(view_paths) > 0:
        st.subheader("🎨 3D Preview Gallery")
        
        # Filter only existing view paths
        existing_view_paths = [vp for vp in view_paths if os.path.exists(vp)]
        
        if existing_view_paths:
            # Show all preview images in columns
            cols = st.columns(2)
            for idx, img_path in enumerate(existing_view_paths):
                col = cols[idx % 2]
                with col:
                    try:
                        st.image(img_path, 
                                caption=f"View {idx+1}: {os.path.basename(img_path)}", 
                                use_container_width=True)
                    except Exception as e:
                        st.error(f"Could not load image {img_path}: {e}")
        else:
            st.info("📷 Preview images were generated but cannot be found. They may have been created in a temporary directory.")
    else:
        st.info("📷 No preview images were generated. This usually happens when no puzzle pieces were created.")

    # ---------- Processing Summary ----------
    with st.expander("📊 Detailed Processing Summary", expanded=True):
        # Parameters used
        st.write("**Parameters Used:**")
        param_df = pd.DataFrame({
            'Parameter': ['X Divisions', 'Y Divisions', 'Z Divisions', 'Locks per Face', 
                         'Cylinder Radius', 'Cylinder Height', 'Sphere Radius', 'Tolerance', 'Random Seed'],
            'Value': [nx, ny, nz, locks_per_face, cyl_radius, cyl_height, sphere_radius, socket_tolerance, seed]
        })
        st.dataframe(param_df, hide_index=True, use_container_width=True)
        
        # Piece generation log
        if st.session_state.progress_data['piece_status']:
            st.write("**Piece Generation Log:**")
            log_text = "\n".join(st.session_state.progress_data['piece_status'])
            st.text_area("Log", log_text, height=200, key="log_area")
        
        # Mesh information
        st.write("**Mesh Information:**")
        mesh_info_df = pd.DataFrame([
            {"Property": "Bounds", "Value": str(mesh_info['bounds'])},
            {"Property": "Watertight", "Value": str(mesh_info['watertight'])},
            {"Property": "Total Pieces Generated", "Value": str(mesh_info['piece_count'])},
            {"Property": "Total Possible Pieces", "Value": str(mesh_info.get('total_possible_pieces', 'N/A'))},
            {"Property": "Success Rate", "Value": str(mesh_info.get('success_rate', 'N/A'))}
        ])
        st.dataframe(mesh_info_df, hide_index=True, use_container_width=True)

# Reset button
if st.session_state.result is not None and not st.session_state.processing:
    if st.button("🔄 Start New Puzzle", use_container_width=True):
        st.session_state.processing = False
        st.session_state.result = None
        st.session_state.progress_data = {
            'current_step': 'Ready',
            'progress': 0,
            'completed_steps': [],
            'piece_status': [],
            'start_time': None
        }
        st.rerun()

# Initial instructions
elif not st.session_state.processing and st.session_state.result is None:
    st.info("""
    **Instructions:**
    1. Upload an STL file
    2. Adjust the grid divisions and interlock parameters in the sidebar
    3. Click 'Generate Puzzle Pieces' to start processing
    4. Wait for the processing to complete (this may take several minutes for complex models)
    5. Download your puzzle pieces and preview images
    """)

st.markdown("---")
st.caption(
    "💡 **Tip:** Start with 2×2×2 divisions and simple STL files for faster processing. "
    "Complex models with many divisions will take longer to process."
)