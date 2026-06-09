"""Gradio web interface for The Unofficial Guide.

User-friendly interface that:
  - Accepts natural language questions about courses/professors
  - Displays grounded answers with source attribution
  - Shows confidence scores and transparency into retrieval
  - Emphasizes that answers are from documents only

Run: python app.py
Then open http://localhost:7860
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import gradio as gr

from src.generate import generate_answer, format_answer_for_display
from src.search import search


def generate_interface_fn(
    query: str, k: int = 5, show_retrieved: bool = True
) -> tuple[str, str, str]:
    """Interface function that Gradio calls.
    
    Args:
        query: User's question
        k: Number of chunks to retrieve
        show_retrieved: Whether to display retrieved chunks
    
    Returns:
        (answer_display, citations_display, retrieved_chunks_display)
    """
    if not query.strip():
        return "Please enter a question.", "", ""

    try:
        # Generate grounded answer
        answer = generate_answer(query, k=k, rerank=True)

        # Format answer for display
        answer_display = format_answer_for_display(answer, verbose=False)

        # Format citations
        if answer.citations:
            citations_list = "\n".join(
                [
                    f"• **{c.source_title}** (Chunk {c.chunk_index}, Distance: {c.distance:.4f})\n"
                    f"  [{c.source_url}]"
                    for c in answer.citations
                ]
            )
        else:
            citations_list = "⚠️ No citations found — answer may not be grounded!"

        # Optionally show retrieved chunks for transparency
        retrieved_display = ""
        if show_retrieved:
            results = search(query, k=k, rerank=True)
            retrieved_lines = ["## Retrieved Chunks (for transparency)\n"]
            for i, result in enumerate(results):
                retrieved_lines.append(f"\n### Chunk {i}: {result.source_title}")
                retrieved_lines.append(
                    f"Distance: {result.distance:.4f} | URL: {result.source_url}\n"
                )
                preview = result.text[:300].replace("\n", " ").strip()
                retrieved_lines.append(f"**Preview:** {preview}...\n")

            retrieved_display = "\n".join(retrieved_lines)

        return answer_display, citations_list, retrieved_display

    except Exception as e:
        error_msg = f"Error: {str(e)}\n\nMake sure GROQ_API_KEY is set and ChromaDB index exists."
        return error_msg, "", ""


# Gradio interface definition
with gr.Blocks(
    title="The Unofficial Guide — Course & Professor Reviews",
) as demo:
    gr.Markdown(
        """
        # 📚 The Unofficial Guide
        ## Course & Professor Reviews (AI-Powered Search)
        
        Ask questions about courses, workload, grading, teaching style, and professor reviews.
        
        **How it works:** Your query is matched against a database of course syllabi, reviews, and
        student experiences using semantic search. Answers are **grounded in the retrieved documents** — 
        the system won't make up information from general knowledge.
        
        ---
        """
    )

    with gr.Row():
        with gr.Column(scale=2):
            query_input = gr.Textbox(
                label="Ask a question",
                placeholder="e.g., 'How many problem sets does CS50 have?'",
                lines=2,
            )
            k_slider = gr.Slider(
                minimum=3,
                maximum=10,
                value=5,
                step=1,
                label="Chunks to retrieve (k)",
                info="More chunks = more context but potentially more noise",
            )
            show_chunks = gr.Checkbox(
                value=True, label="Show retrieved chunks (for transparency)"
            )

            search_button = gr.Button("🔍 Search", size="lg", variant="primary")

            gr.Examples(
                examples=[
                    "How many problem sets does CS50 require?",
                    "Who is MIT 6.0001 designed for?",
                    "What do students say about the workload in CS50?",
                    "How many syllabi does Open Syllabus map?",
                    "Where does Stanford CS107 post course announcements?",
                    "What is the dorm food like at UC Berkeley?",
                ],
                inputs=query_input,
                label="Try one of these:",
            )

        with gr.Column(scale=1):
            gr.Markdown(
                """
                ### Tips
                - **Be specific**: "MIT 6.0001" vs "introductory course"
                - **Ask one thing at a time** for best results
                - **Check sources**: All answers are backed by specific documents
                
                ### Grounding
                Answers come **only from retrieved documents**.
                If the system can't find an answer, it will say so.
                """
            )

    gr.Markdown("---")

    with gr.Tabs():
        with gr.Tab("Answer"):
            answer_output = gr.Textbox(
                label="Generated Answer",
                lines=8,
                interactive=False,
            )

        with gr.Tab("Sources"):
            citations_output = gr.Markdown(label="Citation Details")

        with gr.Tab("Retrieved Chunks"):
            gr.Markdown(
                "*Showing all retrieved chunks — the LLM uses these to generate answers.*"
            )
            chunks_output = gr.Markdown(label="Chunk Details")

    # Wire up the search button
    search_button.click(
        fn=generate_interface_fn,
        inputs=[query_input, k_slider, show_chunks],
        outputs=[answer_output, citations_output, chunks_output],
    )

    # Allow Enter key to trigger search
    query_input.submit(
        fn=generate_interface_fn,
        inputs=[query_input, k_slider, show_chunks],
        outputs=[answer_output, citations_output, chunks_output],
    )

    gr.Markdown(
        """
        ---
        
        ## About Grounding
        
        **The Challenge:** Large language models can hallucinate — generating confident-sounding 
        answers that are completely made up. This happens because they draw on their training data,
        which may be outdated or inaccurate.
        
        **Our Solution:** 
        1. **Retrieval first**: Find the 5 most relevant chunks for your query
        2. **Grounding prompt**: Tell the LLM explicitly to answer ONLY from those chunks
        3. **Citations**: Require the LLM to cite which chunks it used
        4. **Transparency**: Show you the chunks so you can verify the answer
        
        If the LLM tries to use knowledge outside the provided context, it's breaking its 
        instructions — and you'll notice because the answer won't cite any sources.
        
        ### Confidence Score
        - Calculated from retrieval distance (lower = better) and number of sources
        - **80%+ confidence**: Strong evidence in documents
        - **50–79% confidence**: Moderate evidence; check sources
        - **< 50% confidence**: Weak evidence; answer may be incomplete
        """
    )


if __name__ == "__main__":
    demo.launch(
        share=False,
        server_name="127.0.0.1",
        server_port=7860,
        theme=gr.themes.Soft(),
    )
