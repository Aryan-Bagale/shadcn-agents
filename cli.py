# cli.py

import argparse
import importlib
import os
import sys
import requests
from pathlib import Path
from typing import List, Dict, Optional
import tempfile
import json
import subprocess
import time
import importlib.util

# GitHub repository configuration
GITHUB_REPO = "Aryan-Bagale/shadcn-agents"
GITHUB_BRANCH = "main"
TEMPLATES_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/templates"

class ShadcnAgentError(Exception):
    """Base exception for shadcn-agent errors"""
    pass

class TemplateNotFoundError(ShadcnAgentError):
    """Raised when a template cannot be found"""
    pass

class ImportError(ShadcnAgentError):
    """Raised when imports fail"""
    pass

def fetch_template_content(kind: str, name: str) -> str:
    """Fetch template content directly from GitHub and fix imports"""
    url = f"{TEMPLATES_BASE_URL}/{kind}s/{name}.py"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content = response.text
        
        # Fix relative imports in workflow templates
        if kind == "workflow":
            content = fix_template_imports(content)
        
        return content
    except requests.Timeout:
        raise TemplateNotFoundError(f"Timeout fetching template from {url}")
    except requests.RequestException as e:
        raise TemplateNotFoundError(f"Failed to fetch template from {url}: {e}")

def fix_template_imports(content: str) -> str:
    """Fix relative imports in templates to work after being copied"""
    # Replace relative imports with absolute imports
    content = content.replace("from ..nodes.", "from components.nodes.")
    content = content.replace("from ..workflows.", "from components.workflows.")
    
    # Also handle try/except import blocks more robustly
    lines = content.split('\n')
    fixed_lines = []
    
    for line in lines:
        # Skip the fallback import attempts that might not work
        if 'except ImportError:' in line or 'from ..nodes.' in line or 'from ..workflows.' in line:
            # Keep the except block but improve error message
            if 'except ImportError as e:' in line:
                fixed_lines.append(line)
            elif 'raise ImportError(' in line:
                fixed_lines.append(line)
            # Skip the problematic relative import fallbacks
            elif 'from ..' in line and 'import' in line:
                continue
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fetch_available_templates() -> Dict[str, List[str]]:
    """Fetch list of available templates from GitHub API"""
    try:
        # Fetch nodes
        nodes_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/templates/nodes"
        nodes_response = requests.get(nodes_url, timeout=10)
        nodes_response.raise_for_status()
        nodes = [item['name'].replace('.py', '') for item in nodes_response.json() 
                if item['name'].endswith('.py') and item['type'] == 'file']
        
        # Fetch workflows
        workflows_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/templates/workflows"
        workflows_response = requests.get(workflows_url, timeout=10)
        workflows_response.raise_for_status()
        workflows = [item['name'].replace('.py', '') for item in workflows_response.json() 
                    if item['name'].endswith('.py') and item['type'] == 'file']
        
        return {"nodes": nodes, "workflows": workflows}
    except requests.RequestException as e:
        print(f"⚠️  Could not fetch template list from GitHub: {e}")
        print("📡 Using fallback template list...")
        # Fallback list of known templates
        return {
            "nodes": ["search_node", "summarizer_node", "translate_node", "email_node"],
            "workflows": ["summarize_and_email_graph", "translate_and_email_graph", "scrape_and_summarize_graph"]
        }

def get_library_dir(dest: Optional[str] = None) -> Path:
    """Get the library directory path"""
    return Path(dest or "components")

def library_items(kind: str, dest: Optional[str] = None) -> List[str]:
    """List existing library items"""
    p = get_library_dir(dest) / (kind + "s")
    if not p.exists():
        return []
    return [f.stem for f in p.glob("*.py") if not f.name.startswith('__')]

def validate_workflow_inputs(workflow_name: str, inputs: Dict) -> List[str]:
    """Validate inputs for specific workflows"""
    errors = []
    
    required_inputs = {
        "summarize_and_email_graph": [("url", "URL")],
        "translate_and_email_graph": [("text", "text"), ("target_lang", "target language")],
        "scrape_and_summarize_graph": [("url", "URL")]
    }
    
    if workflow_name in required_inputs:
        for param, description in required_inputs[workflow_name]:
            if not inputs.get(param):
                errors.append(f"'{workflow_name}' requires --{param} parameter ({description})")
    
    return errors

def add_component(kind: str, name: str, dest_folder: Optional[str] = None) -> bool:
    """Add a component by fetching it from GitHub"""
    dest_dir = get_library_dir(dest_folder) / (kind + "s")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{name}.py"

    if dest.exists():
        print(f"⚠️  {name}.py already exists in {dest_dir}/")
        try:
            response = input("Overwrite? (y/N): ").strip().lower()
            if response != 'y':
                print("❌ Cancelled.")
                return False
        except (EOFError, KeyboardInterrupt):
            print("\n❌ Cancelled.")
            return False

    try:
        print(f"📡 Fetching {kind} template: {name}...")
        content = fetch_template_content(kind, name)
        
        # Ensure proper encoding when writing
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Added {kind}: {name} to {dest_dir}")
        return True
    except TemplateNotFoundError as e:
        print(f"❌ Template not found: {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to add {kind} '{name}': {e}")
        return False

def list_all(dest_folder: Optional[str] = None):
    """List available templates and local components"""
    lib_name = dest_folder or "components"
    
    print("📡 Fetching available templates...")
    try:
        available = fetch_available_templates()
        
        print("\n=== Available Templates (from GitHub) ===")
        print("📦 Nodes:")
        for node in sorted(available["nodes"]):
            print(f"  • {node}")
        print("\n🔄 Workflows:")
        for wf in sorted(available["workflows"]):
            print(f"  • {wf}")
    except Exception as e:
        print(f"❌ Could not fetch available templates: {e}")

    print(f"\n=== Your {lib_name}/ Library ===")
    lib_dir = get_library_dir(dest_folder)
    if not lib_dir.exists():
        print(f"📁 Library folder '{lib_name}' not found.")
        print(f"💡 Initialize with: shadcn-agent init --dest {lib_name}")
        return
    
    nodes = library_items("node", dest_folder)
    workflows = library_items("workflow", dest_folder)
    
    print("📦 Nodes:")
    if nodes:
        for node in sorted(nodes):
            print(f"  • {node}")
    else:
        print("  (none)")
    
    print("\n🔄 Workflows:")
    if workflows:
        for wf in sorted(workflows):
            print(f"  • {wf}")
    else:
        print("  (none)")

def safe_import_workflow(name: str, lib_folder: str) -> Optional[callable]:
    """Safely import a workflow module with better error handling"""
    lib_dir = get_library_dir(lib_folder)
    workflow_file = lib_dir / "workflows" / f"{name}.py"
    
    if not workflow_file.exists():
        return None
    
    # Add the project root to Python path
    project_root = lib_dir.parent.absolute()
    original_path = sys.path.copy()
    
    try:
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # Use importlib.util for more robust importing
        module_name = f"{lib_folder}.workflows.{name}"
        spec = importlib.util.spec_from_file_location(module_name, workflow_file)
        
        if spec is None or spec.loader is None:
            return None
        
        module = importlib.util.module_from_spec(spec)
        
        # Clear from sys.modules to ensure fresh import
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        return getattr(module, "build_workflow", None)
        
    except Exception as e:
        print(f"❌ Import error for workflow '{name}': {e}")
        return None
    finally:
        # Restore original path
        sys.path[:] = original_path

def run_workflow(name: str, inputs: Dict, dest_folder: Optional[str] = None) -> bool:
    """Run a workflow from the user's project"""
    lib_folder = dest_folder or "components"
    lib_dir = get_library_dir(dest_folder)
    
    # Validate library exists
    if not lib_dir.exists():
        print(f"❌ The library folder '{lib_folder}' does not exist.")
        print(f"💡 Initialize it with: shadcn-agent init --dest {lib_folder}")
        return False

    # Check if workflow exists
    workflow_file = lib_dir / "workflows" / f"{name}.py"
    if not workflow_file.exists():
        print(f"❌ Workflow '{name}' not found in {lib_folder}/workflows/")
        print(f"💡 Add it with: shadcn-agent add workflow {name} --dest {lib_folder}")
        return False
    
    # Validate required inputs
    validation_errors = validate_workflow_inputs(name, inputs)
    if validation_errors:
        print("❌ Input validation failed:")
        for error in validation_errors:
            print(f"   {error}")
        return False

    try:
        builder = safe_import_workflow(name, lib_folder)
        
        if builder is None:
            print(f"❌ Could not import workflow '{name}' or it doesn't expose build_workflow() function")
            return False

        print(f"🚀 Running workflow: {name} from {lib_folder}")
        print(f"📥 Inputs: {inputs}")
        
        app = builder()
        step_count = 0
        
        for step in app.stream(inputs):
            step_count += 1
            print(f"📊 Step {step_count} Output:", step)
        
        print("✅ Workflow completed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error for workflow '{name}': {e}")
        print(f"💡 Make sure all required nodes are added to {lib_folder}/nodes/")
        return False
    except Exception as e:
        print(f"❌ Error running workflow '{name}': {e}")
        return False

def init_project(dest_folder: Optional[str] = None) -> bool:
    """Initialize a new shadcn-agent project with basic structure"""
    lib_folder = dest_folder or "components"
    lib_dir = get_library_dir(dest_folder)
    
    try:
        # Create the directory structure
        (lib_dir / "nodes").mkdir(parents=True, exist_ok=True)
        (lib_dir / "workflows").mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py files to make it a proper Python package
        (lib_dir / "__init__.py").write_text("# shadcn-agent components\n", encoding='utf-8')
        (lib_dir / "nodes" / "__init__.py").write_text("# Agent nodes\n", encoding='utf-8')
        (lib_dir / "workflows" / "__init__.py").write_text("# Agent workflows\n", encoding='utf-8')
        
        print(f"✅ Initialized shadcn-agent project structure in {lib_folder}/")
        print(f"📁 Created directories:")
        print(f"   • {lib_folder}/nodes/")
        print(f"   • {lib_folder}/workflows/")
        print(f"💡 Next steps:")
        print(f"   • shadcn-agent add node search_node --dest {lib_folder}")
        print(f"   • shadcn-agent add workflow summarize_and_email_graph --dest {lib_folder}")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize project: {e}")
        return False

def run_playground() -> bool:
    """Run the shadcn-agent playground using the packaged version"""
    try:
        # Get the path to the packaged playground.py
        package_dir = Path(__file__).parent
        playground_path = package_dir / "playground.py"
        
        if not playground_path.exists():
            print("❌ Playground not found in package. Please reinstall shadcn-agent.")
            print("💡 Try: pip install --upgrade shadcn-agent")
            return False
        
        print("🚀 Starting shadcn-agent playground...")
        print(f"📁 Looking for components in current directory")
        print("💡 Tip: Run this in a directory with your shadcn-agent components")
        print("🌐 Opening browser...")
        
        # Run streamlit with the packaged playground
        result = subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            str(playground_path),
            "--server.headless", "false",
            "--server.port", "8501"
        ], check=False)
        
        return result.returncode == 0
        
    except KeyboardInterrupt:
        print("\n👋 Playground stopped by user.")
        return True
    except FileNotFoundError:
        print("❌ Streamlit not found. Install it with: pip install streamlit")
        print("💡 Or install with all dependencies: pip install shadcn-agent[dev]")
        return False
    except Exception as e:
        print(f"❌ Failed to start playground: {e}")
        return False

def create_config(dest_folder: Optional[str] = None) -> bool:
    """Create a .shadcn-agent.json config file"""
    config = {
        "components_dir": dest_folder or "components",
        "github_repo": GITHUB_REPO,
        "github_branch": GITHUB_BRANCH,
        "version": "0.2.0"
    }
    
    try:
        with open('.shadcn-agent.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print("✅ Created .shadcn-agent.json config file")
        return True
    except Exception as e:
        print(f"❌ Failed to create config file: {e}")
        return False

def load_config() -> Dict:
    """Load configuration from .shadcn-agent.json if it exists"""
    config_file = Path(".shadcn-agent.json")
    if config_file.exists():
        try:
            with open(config_file, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load config file: {e}")
    return {}

def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="shadcn-agent: Build composable AI agents with copy-paste components from GitHub.",
        epilog="Examples:\n"
               "  shadcn-agent init --dest my_agents\n"
               "  shadcn-agent add node summarizer_node --dest my_agents\n"
               "  shadcn-agent add workflow summarize_and_email_graph --dest my_agents\n"
               "  shadcn-agent run workflow summarize_and_email_graph --dest my_agents --url https://example.com\n"
               "  shadcn-agent playground",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    sub = parser.add_subparsers(dest="cmd", help="Available commands")

    # Init command
    parser_init = sub.add_parser("init", help="Initialize a new shadcn-agent project structure")
    parser_init.add_argument("--dest", default=None, help="Destination folder (default: components)")
    parser_init.add_argument("--config", action="store_true", help="Create .shadcn-agent.json config file")

    # Add command
    parser_add = sub.add_parser("add", help="Add a node or workflow template from GitHub")
    parser_add.add_argument("kind", choices=["node", "workflow"], help="Type of component to add")
    parser_add.add_argument("name", help="Name of template (without .py extension)")
    parser_add.add_argument("--dest", default=None, help="Destination folder (default: components)")

    # List command
    parser_list = sub.add_parser("list", help="List available templates and your local components")
    parser_list.add_argument("--dest", default=None, help="Project folder to list (default: components)")

    # Run command
    parser_run = sub.add_parser("run", help="Run a workflow from your project")
    parser_run.add_argument("kind", choices=["workflow"], help="Type of component to run")
    parser_run.add_argument("name", help="Name of workflow to run")
    parser_run.add_argument("--dest", default=None, help="Project folder (default: components)")
    parser_run.add_argument("--url", default=None, help="URL input for the workflow")
    parser_run.add_argument("--text", default=None, help="Text input for the workflow")
    parser_run.add_argument("--target_lang", default=None, help="Target language (for translate workflows)")
    parser_run.add_argument("--recipient", default=None, help="Recipient email address")

    # Playground command
    parser_playground = sub.add_parser("playground", help="Run the interactive playground app")

    args = parser.parse_args(argv)

    # Handle case where no command is provided
    if args.cmd is None:
        parser.print_help()
        return 1

    # Load config
    config = load_config()
    
    # Execute commands
    try:
        if args.cmd == "init":
            success = init_project(args.dest)
            if success and args.config:
                create_config(args.dest)
            return 0 if success else 1
            
        elif args.cmd == "add":
            success = add_component(args.kind, args.name, args.dest)
            return 0 if success else 1
            
        elif args.cmd == "list":
            list_all(args.dest)
            return 0
            
        elif args.cmd == "run":
            # Collect inputs
            inputs = {}
            if args.url is not None:
                inputs["url"] = args.url
            if args.text is not None:
                inputs["text"] = args.text
            if args.target_lang is not None:
                inputs["target_lang"] = args.target_lang
            if args.recipient is not None:
                inputs["recipient"] = args.recipient
            
            success = run_workflow(args.name, inputs, args.dest)
            return 0 if success else 1
            
        elif args.cmd == "playground":
            success = run_playground()
            return 0 if success else 1
            
    except KeyboardInterrupt:
        print("\n👋 Operation cancelled by user.")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())