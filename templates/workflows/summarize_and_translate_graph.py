# ===== templates/workflows/summarize_and_translate_graph.py =====
from langgraph.graph import StateGraph, END
from typing import Dict

def build_workflow():
    """Build the summarize + translate workflow."""

    # Import nodes with error handling
    try:
        from components.nodes.summarizer_node import summarizer_node
        from components.nodes.translate_node import translate_node
    except ImportError as e:
        raise ImportError(
            f"Could not import required nodes: {e}\n"
            "Make sure to add the required components:\n"
            "  shadcn-agent add node summarizer_node\n"
            "  shadcn-agent add node translate_node"
        )

    workflow = StateGraph(dict)
    workflow.add_node("summarizer", summarizer_node)
    workflow.add_node("translator", translate_node)

    workflow.set_entry_point("summarizer")
    workflow.add_edge("summarizer", "translator")
    workflow.add_edge("translator", END)

    return workflow.compile()
