import streamlit as st
import os
import sys
from pathlib import Path
import importlib
import importlib.util
import json
from typing import Optional, Dict, Any, List

# Load environment variables if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure Streamlit page
st.set_page_config(
    page_title="shadcn-agent Playground",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sidebar for library folder selection
default_lib = os.environ.get("SHADCN_AGENT_LIB", "components")
lib_folder = st.sidebar.text_input("Library Folder", default_lib)

# Add current working directory to Python path for importing user's components
cwd = Path.cwd()
if str(cwd) not in sys.path:
    sys.path.insert(0, str(cwd))

@st.cache_data
def get_available_workflows(library_folder: str) -> List[str]:
    """Get list of available workflow files"""
    workflows_path = Path(library_folder) / "workflows"
    if not workflows_path.exists():
        return []
    
    workflows = []
    for py_file in workflows_path.glob("*.py"):
        if not py_file.name.startswith("__"):
            workflows.append(py_file.stem)
    return workflows

@st.cache_data
def get_available_nodes(library_folder: str) -> List[str]:
    """Get list of available node files"""
    nodes_path = Path(library_folder) / "nodes"
    if not nodes_path.exists():
        return []
    
    nodes = []
    for py_file in nodes_path.glob("*.py"):
        if not py_file.name.startswith("__"):
            nodes.append(py_file.stem)
    return nodes

def safe_import_workflow(workflow_name: str, library_folder: str) -> Optional[callable]:
    """Safely import workflow with better error handling"""
    try:
        workflow_file = Path(library_folder) / "workflows" / f"{workflow_name}.py"
        if not workflow_file.exists():
            return None
        
        module_name = f"{library_folder}.workflows.{workflow_name}"
        
        # Use importlib.util for more robust importing
        spec = importlib.util.spec_from_file_location(module_name, workflow_file)
        
        if spec is None or spec.loader is None:
            return None
        
        # Force reload in case user modified the workflow
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        return getattr(module, "build_workflow", None)
    except Exception as e:
        st.error(f"Could not import workflow '{workflow_name}': {e}")
        return None

def safe_import_node(node_name: str, library_folder: str) -> Optional[callable]:
    """Safely import node with better error handling"""
    try:
        node_file = Path(library_folder) / "nodes" / f"{node_name}.py"
        if not node_file.exists():
            return None
        
        module_name = f"{library_folder}.nodes.{node_name}"
        
        # Use importlib.util for more robust importing
        spec = importlib.util.spec_from_file_location(module_name, node_file)
        
        if spec is None or spec.loader is None:
            return None
        
        # Force reload in case user modified the node
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        return getattr(module, node_name, None)
    except Exception as e:
        st.error(f"Could not import node '{node_name}': {e}")
        return None

def check_library_exists(library_folder: str) -> bool:
    """Check if the library folder exists"""
    lib_path = Path(library_folder)
    if not lib_path.exists():
        st.error(f"📁 Library folder '{library_folder}' not found!")
        st.info(f"💡 Initialize it first: `shadcn-agent init --dest {library_folder}`")
        return False
    return True

def download_json_results(results: List[Dict], filename: str):
    """Create download button for JSON results"""
    json_str = json.dumps(results, indent=2, default=str)
    st.download_button(
        "💾 Download Results as JSON", 
        data=json_str, 
        file_name=filename,
        mime="application/json"
    )

def run_predefined_workflow(workflow_name: str, display_name: str, description: str, 
                           input_fields: Dict[str, Any], library_folder: str):
    """Run a predefined workflow with error handling"""
    st.markdown(f"### {display_name}")
    st.markdown(description)
    
    # Create input fields
    inputs = {}
    for field_name, field_config in input_fields.items():
        if field_config["type"] == "text_input":
            inputs[field_name] = st.text_input(field_config["label"], field_config["default"])
        elif field_config["type"] == "text_area":
            inputs[field_name] = st.text_area(field_config["label"], field_config["default"])
    
    if st.button(f"🚀 Run {display_name}", type="primary", key=workflow_name):
        build_workflow = safe_import_workflow(workflow_name, library_folder)
        
        if build_workflow:
            with st.spinner(f"Running {display_name}..."):
                try:
                    app = build_workflow()
                    st.write("## 📊 Workflow Output:")
                    
                    results = []
                    step_container = st.container()
                    
                    for step in app.stream(inputs):
                        with step_container:
                            st.json(step)
                        results.append(step)
                    
                    download_json_results(results, f"{workflow_name}_results.json")
                    st.success(f"✅ {display_name} completed!")
                    
                except Exception as e:
                    st.error(f"❌ {display_name} failed: {e}")
                    if st.checkbox("Show detailed error", key=f"{workflow_name}_debug"):
                        st.exception(e)
        else:
            st.error(f"Workflow not available in '{library_folder}'. Add it first:")
            st.code(f"shadcn-agent add workflow {workflow_name} --dest {library_folder}")

def main():
    st.title("🤖 shadcn-agent Playground")
    st.markdown("*Test your AI workflows in an interactive environment*")
    
    if not check_library_exists(lib_folder):
        st.stop()
    
    # Get available components
    available_workflows = get_available_workflows(lib_folder)
    available_nodes = get_available_nodes(lib_folder)
    
    if not available_workflows and not available_nodes:
        st.warning(f"No components found in '{lib_folder}'. Add some components first!")
        st.code(f"""
# Add some components
shadcn-agent add node search_node --dest {lib_folder}
shadcn-agent add workflow summarize_and_email_graph --dest {lib_folder}
        """)
        st.stop()
    
    # Workflow selection
    workflow_options = [
        "Summarize + Email", 
        "Translate + Email", 
        "Scrape + Summarize", 
        "Custom Workflow Builder"
    ]
    
    workflow = st.selectbox("Choose a workflow", workflow_options)
    
    if workflow == "Summarize + Email":
        run_predefined_workflow(
            "summarize_and_email_graph",
            "🔗 Summarize + Email Workflow",
            "Scrapes a URL → Summarizes content → Sends email",
            {
                "url": {"type": "text_input", "label": "URL to summarize", 
                       "default": "https://en.wikipedia.org/wiki/Artificial_intelligence"},
                "recipient": {"type": "text_input", "label": "Recipient Email", 
                             "default": os.getenv("DEFAULT_RECIPIENT", "test@example.com")}
            },
            lib_folder
        )
    
    elif workflow == "Translate + Email":
        run_predefined_workflow(
            "translate_and_email_graph",
            "🌐 Translate + Email Workflow", 
            "Translates text → Sends email",
            {
                "text": {"type": "text_area", "label": "Text to translate", 
                        "default": "Hello, how are you?"},
                "target_lang": {"type": "text_input", "label": "Target Language (e.g., fr, es, de)", 
                               "default": "fr"},
                "recipient": {"type": "text_input", "label": "Recipient Email", 
                             "default": os.getenv("DEFAULT_RECIPIENT", "test@example.com")}
            },
            lib_folder
        )
    
    elif workflow == "Scrape + Summarize":
        run_predefined_workflow(
            "scrape_and_summarize_graph",
            "🔍 Scrape + Summarize Workflow",
            "Scrapes a URL → Summarizes content", 
            {
                "url": {"type": "text_input", "label": "URL to scrape and summarize", 
                       "default": "https://en.wikipedia.org/wiki/Artificial_intelligence"}
            },
            lib_folder
        )
    
    elif workflow == "Custom Workflow Builder":
        st.markdown("### 🛠️ Custom Workflow Builder")
        st.info("Select nodes and chain them to build your own workflow.")
        
        if not available_nodes:
            st.warning(f"No nodes found in '{lib_folder}/nodes/'. Add some nodes first!")
            st.code(f"shadcn-agent add node search_node --dest {lib_folder}")
            st.stop()
        
        # Node configuration mapping
        node_options = {
            "search_node": ("🔍 Search (Web Scraper)", "url"),
            "summarizer_node": ("📝 Summarizer", "text"),
            "translate_node": ("🌐 Translator", "text"),
            "email_node": ("📧 Email Sender", "body")
        }
        
        # Filter available nodes
        available_node_options = {k: v for k, v in node_options.items() if k in available_nodes}
        
        if not available_node_options:
            st.warning("No recognized node types found. Available nodes:")
            for node in available_nodes:
                st.write(f"• {node}")
            st.stop()
        
        selected_nodes = st.multiselect(
            "Select nodes to include (order matters):",
            options=list(available_node_options.keys()),
            format_func=lambda n: available_node_options[n][0],
            default=["search_node", "summarizer_node"] if all(n in available_nodes for n in ["search_node", "summarizer_node"]) else []
        )
        
        # Input fields for the first node
        user_inputs = {}
        if selected_nodes:
            first_node = selected_nodes[0]
            st.markdown(f"### Input for {available_node_options[first_node][0]}")
            
            if first_node == "search_node":
                user_inputs["url"] = st.text_input("URL", "https://en.wikipedia.org/wiki/Artificial_intelligence")
            elif first_node in ["summarizer_node", "translate_node"]:
                user_inputs["text"] = st.text_area("Text", "Hello, world!")
                if first_node == "translate_node":
                    user_inputs["target_lang"] = st.text_input("Target Language", "fr")
            elif first_node == "email_node":
                user_inputs["body"] = st.text_area("Email Body", "This is a test email.")
                user_inputs["recipient"] = st.text_input("Recipient Email", 
                                                        os.getenv("DEFAULT_RECIPIENT", "test@example.com"))
        
        if st.button("🚀 Run Custom Workflow", type="primary") and selected_nodes:
            # Import node functions
            node_funcs = {}
            missing_nodes = []
            
            for node in selected_nodes:
                func = safe_import_node(node, lib_folder)
                if func is None:
                    missing_nodes.append(node)
                else:
                    node_funcs[node] = func
            
            if missing_nodes:
                st.error(f"Missing nodes: {', '.join(missing_nodes)}")
                for node in missing_nodes:
                    st.code(f"shadcn-agent add node {node} --dest {lib_folder}")
                st.stop()
            
            with st.spinner("Running custom workflow..."):
                try:
                    state = user_inputs.copy()
                    results = []
                    
                    st.write("## 📊 Custom Workflow Output:")
                    for i, node in enumerate(selected_nodes):
                        func = node_funcs[node]
                        state = func(state)
                        
                        step_result = {f"Step {i+1} - {available_node_options[node][0]}": state}
                        st.json(step_result)
                        results.append(step_result)
                    
                    download_json_results(results, "custom_workflow_results.json")
                    st.success("✅ Custom workflow completed!")
                    
                except Exception as e:
                    st.error(f"❌ Custom workflow failed: {e}")
                    if st.checkbox("Show detailed error", key="custom_debug"):
                        st.exception(e)
    
    # Sidebar info
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📚 Quick Setup")
        st.code(f"""
# Initialize project
shadcn-agent init --dest {lib_folder}

# Add components  
shadcn-agent add node search_node --dest {lib_folder}
shadcn-agent add workflow scrape_and_summarize_graph --dest {lib_folder}
        """)
        
        st.markdown("### 🔧 Environment Setup")
        st.markdown("Create `.env` file:")
        st.code("""
SENDER_EMAIL=your@email.com
SENDER_PASSWORD=your_app_password
DEFAULT_RECIPIENT=recipient@example.com
        """)
        
        st.markdown("### 📊 Component Status")
        st.write(f"**Workflows:** {len(available_workflows)}")
        for wf in available_workflows:
            st.write(f"  • {wf}")
        
        st.write(f"**Nodes:** {len(available_nodes)}")
        for node in available_nodes:
            st.write(f"  • {node}")

if __name__ == "__main__":
    main()