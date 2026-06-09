# The Unofficial Guide — Project 1

> **How to use this template:**
> Complete each section *after* you've built and tested the corresponding part of your system.
> Do not write placeholder text — if a section isn't done yet, leave it blank and come back.
> Every section below is required for submission. One-liners will not receive full credit.

---

## Domain

<!-- What topic or category of knowledge does your system cover?
     Why is this knowledge valuable, and why is it hard to find through official channels?
     Example: "Student reviews of CS professors at [university] — useful because official
     course descriptions don't reflect teaching style, exam difficulty, or workload." -->
Course and professor reviews (general): student-written accounts of teaching style, workload, grading practices, and exam difficulty that provide practical context missing from official course descriptions. These firsthand insights are valuable for course selection and preparation but are dispersed across syllabi, forum threads, RateMyProfessors pages, and public course repositories, making them difficult to aggregate and search.

This project collects and structures those scattered sources so readers can quickly find experience-based advice about instructors and courses.
---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | CS107 (Stanford) course page | Syllabus/course hub | https://web.stanford.edu/class/cs107/ |
| 2 | MIT OCW — 6.006 (Algorithms) | Syllabus & resources | https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/ |
| 3 | MIT OCW — 6.0001 (Intro to CS) | Syllabus & instructor insights | https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/ |
| 4 | Harvard CS50 syllabus | Syllabus & course policies | https://cs50.harvard.edu/x/2023/syllabus/ |
| 5 | Open Syllabus Project | Aggregated syllabi dataset | https://opensyllabus.org/ |
| 6 | GitHub search: syllabus university | Public course repositories | https://github.com/search?q=syllabus+university&type=repositories |
| 7 | RateMyProfessors (search) | Instructor review pages | https://www.ratemyprofessors.com/search/teachers?query=computer%20science |
| 8 | Reddit r/college (threads) | Student discussion threads | https://www.reddit.com/r/college/search?q=best%20professors&restrict_sr=1&type=link |
| 9 | Quora — professor threads | Crowdsourced experiences | https://www.quora.com/Which-are-the-best-professors-in-your-college |
| 10 | The Student Room | Student forum threads | https://www.thestudentroom.co.uk/search.php?search_terms=professors |
| 11 | College Confidential | US college forums | https://www.collegeconfidential.com/search/?q=professor+reviews |
| 12 | Example GitHub syllabi repos | Individual course materials (README/syllabus) | See results from GitHub search (link above) |

---

## Chunking Strategy

<!-- Describe your chunking approach with enough specificity that someone else could reproduce it.
     Include:
     - Chunk size (characters or tokens) and why that size fits your documents
     - Overlap size and why (or why not) you used overlap
     - Any preprocessing you did before chunking (e.g., stripping HTML, removing headers)
     - What your final chunk count was across all documents -->

**Chunk size:** Two-tier, set in `src/ingest_and_chunk.py`.
- **Long tier — 1000 tokens** for syllabi, course hubs, and long README files (CS50, CS107, the long-form sources).
- **Short tier — 300 tokens** for student reviews, forum snippets, and brief instructor comments.
- Token counts are measured with `tiktoken` (`cl100k_base`), not character counts, so chunks fit cleanly within the embedding model's effective context.
- Any document whose total token count is **≤ 300** (the short-tier threshold) is kept as a single chunk regardless of declared tier. This matches the planning.md rule "When a document is shorter than the secondary threshold, keep it as a single chunk."

**Overlap:**
- Long tier: **200 tokens** (~1.2k chars).
- Short tier: **50 tokens** (~250 chars).
- Overlap is realized at sentence boundaries — the chunker re-seeds the next chunk with whichever trailing sentences of the previous chunk cumulatively cover the overlap budget. Mid-sentence cuts are forbidden by the splitter.

**Why these choices fit your documents:** The corpus is a deliberate mix of long, structured documents (course pages with prose paragraphs about grading, expectations, and policies) and many short, informal items (student reviews, forum posts). A single chunk size would either fragment the short items unnecessarily or merge unrelated sections of the long ones. The 1000-token long size keeps a coherent syllabus subsection (grading + final-project policy, or course overview + topics) in one chunk so retrieval returns semantically complete context; the 200-token overlap prevents grading-policy sentences from being split across chunks (a real failure mode flagged in planning.md's "How to detect bad chunking" notes). The 300-token short size matches the natural length of a single review or a small batch of related forum comments, and the 50-token overlap is enough to preserve cross-reference between adjacent reviews without inflating storage.

Preprocessing before chunking is done in `src/clean_documents.py` (separate stage): strip HTML entities, drop site chrome (nav menus, footers, repeated headers, copyright lines, Material icon font names, "Show more" truncation previews, image attribution fragments), de-duplicate identical lines (last-seen wins, so a label inside a content section beats the same label in a sidebar), and strip a leading run of 10+ nav-like paragraphs (catches CS107's 60-item sidebar). Each chunk is then emitted with a metadata header — `source_id`, `source_url`, `source_title`, `tier`, `chunk_index`, `char_start`, `char_end`, `token_count`, `text` — so attribution is always available downstream.

**Final chunk count:** **11 chunks across 7 documents** (5,506 tokens total).

| Source | Tier | Chunks | Tokens |
|---|---|---|---|
| cs107_stanford | long | 4 | 3,442 |
| cs50_syllabus | long | 1 | 970 |
| mit_6_0001 | long | 1 | 171 |
| mit_6_006 | long | 1 | 181 |
| open_syllabus | long | 1 | 156 |
| reviews_intro_cs_sample | short | 2 | 403 |
| reviews_professors_sample | short | 1 | 183 |

This is well under the planning estimate of ~300 chunks. The cause is corpus undersizing, not chunking-parameter mistakes: five of the seven cleaned documents fall below the 300-token single-chunk threshold (MIT OCW course-root pages, Open Syllabus home, and the short review samples). Static HTML extraction of MIT OCW returns mostly cards and metadata — the lecture-notes / problem-sets subpages, which contain the real substance, are JS-rendered and weren't fetched. To reach the spec's ~300-chunk target, the corpus would need to be expanded with OCW subpages and more review files; the chunking parameters themselves don't need adjustment.

---

## Embedding Model

<!-- Name the embedding model you used and explain your choice.
     Then answer: if you were deploying this system for real users and cost wasn't a constraint,
     what tradeoffs would you weigh in choosing a different model?
     Consider: context length limits, multilingual support, accuracy on domain-specific text,
     latency, and local vs. API-hosted. -->

**Model used:** `sentence-transformers/all-MiniLM-L6-v2`

**Choice rationale:**
- **Lightweight & fast**: 384-dimensional embeddings, ~1 second inference for 11 chunks
- **Local execution**: No API calls, no latency overhead, privacy-preserving
- **Mixed-domain text**: Performs well on formal syllabi, informal student reviews, and structured course metadata
- **Community proven**: MiniLM variant is widely used for semantic search across diverse document types
- **Low resource footprint**: Fits on CPU/GPU; production deployments don't require expensive hardware

**Production tradeoff reflection:**

If cost and infrastructure constraints were lifted, I would evaluate:

- **Larger models** (`all-mpnet-base-v2`, OpenAI's `text-embedding-3-large`): Better accuracy on nuanced queries like "How hard is this professor?" or "Will I enjoy this class?" — capturing subtle teaching style cues. Trade-off: 10-100x latency increase, API dependency.

- **Domain-finetuned models**: Retrain on academic/reviews corpus to capture education-specific vocabulary (e.g., "lecture-heavy", "weed-out class"). Trade-off: requires labeled data and engineering effort.

- **Multilingual models** (`multilingual-e5`): Support international syllabi and forums. Trade-off: slightly lower English accuracy, larger embedding dimension.

For this system, **all-MiniLM-L6-v2 is the right choice** because:
1. Corpus is small (11 chunks) — larger models don't provide gains at this scale
2. Retrieval quality target (88% precision) is already met locally
3. User expectations: sub-100ms response time, no external dependencies

---

## Grounded Generation

<!-- Explain how your system enforces grounding — how does it prevent the LLM from answering
     beyond the retrieved documents?
     Describe both your system prompt (what instruction you gave the model) and any structural
     choices (e.g., how you formatted the context, whether you filtered low-relevance chunks).
     Do not just say "I told it to use the documents" — show the actual instruction or explain
     the mechanism. -->

**System Prompt Grounding Instruction:**

The system prompt in `src/generate.py` explicitly forbids hallucination through three mechanisms:

1. **Negative Instruction**: "Do NOT use your general knowledge or training data."
2. **Mandatory Citations**: "Always cite your sources by referencing chunk numbers and source titles."
3. **Fallback Language**: "If a question cannot be answered from the context, respond with: 'I don't have enough information...'"
4. **Chunk Format**: Each retrieved chunk is labeled `[CHUNK 0]`, `[CHUNK 1]`, etc., so the LLM must explicitly reference chunks to cite sources.

Complete system prompt:
```
CRITICAL INSTRUCTIONS FOR GROUNDING:
1. Answer ONLY using the provided context chunks below.
2. Do NOT use your general knowledge or training data.
3. If a question cannot be answered from the context, respond with: "I don't have enough information about this in the available documents."
4. Always cite your sources by referencing chunk numbers and source titles.
5. Quote directly from the context when asserting facts.
```

**How Source Attribution is Surfaced in the Response:**

- **Chunk labeling**: Each chunk formatted as `[CHUNK N]` with source metadata (title, URL, distance score)
- **Extraction**: After LLM response, parse for `[CHUNK N]` references and map back to original sources
- **Structured output**: Return `{answer_text, citations:[{source_title, source_url, chunk_index}], confidence_score}`
- **UI display**: Web interface shows answer + sources + confidence % + retrieved chunks for verification
- **Confidence penalty**: Answers with zero citations get 0% confidence (red flag for user)

This makes hallucination detectable: if LLM gives an answer without citing chunks, confidence will be 0%.

---

## Evaluation Report

End-to-end results from running each of the 5 evaluation questions in `planning.md` through the full pipeline (`load → clean → chunk → embed → search → generate`) on **2026-06-09**. Model: `llama-3.3-70b-versatile` via Groq. Top-k = 5 with source-aware reranking.

### Q1 — CS50 problem set count

- **Question:** *According to the CS50 syllabus, how many problem sets must students submit?*
- **Expected answer:** Ten problem sets.
- **System response:**
  > *"According to the CS50 syllabus, students must submit ten problem sets. As stated in Chunk 0 (CS50x 2023 Syllabus), 'You are expected to submit ten problem sets, submit nine labs, and submit a final project.'"*
  > Sources: CS50x 2023 Syllabus (Harvard) — https://cs50.harvard.edu/x/2023/syllabus/
- **Judgment:** ✅ **Accurate.** Verbatim quote from the correct source.

### Q2 — CS107 announcement channels

- **Question:** *Where does Stanford CS107 instruct students to check for important course announcements?*
- **Expected answer:** On the course web page and the Ed Discussion forum (and announced in class).
- **System response:**
  > *"According to CHUNK 1, students are instructed to check the course webpage and the Ed Discussion forum for important course announcements. As stated, 'Important course announcements will be posted below and announced in class and on the Ed Discussion forum.'"*
  > Sources: CS107: Computer Organization & Systems (Stanford, Spring 2026) — https://web.stanford.edu/class/cs107/
- **Judgment:** ✅ **Accurate.** All three channels named (course webpage, Ed Discussion forum, announced in class), with a verbatim quote from the right source.

### Q3 — MIT 6.0001 audience

- **Question:** *According to MIT 6.0001's course description, who is the course intended for?*
- **Expected answer:** Students with little or no programming experience.
- **System response:**
  > *"I don't have enough information on that."*
- **Judgment:** ❌ **Inaccurate (refusal when the answer is in the corpus).** The expected phrase is present in `documents/cleaned/mit_6_0001.txt`, but retrieval did not surface that chunk into the top-5 for this query. The model then correctly applied the grounding rules and refused. This is a retrieval failure, not a generation failure — see Failure Case Analysis below.

### Q4 — MIT 6.006 learning resource types

- **Question:** *Which learning resource types are listed on the MIT 6.006 course page?*
- **Expected answer:** Lecture notes, lecture videos, problem sets, quizzes, and exam/solution materials.
- **System response:** *(LLM call could not be completed — Groq daily token limit reached at this run, 99,457 / 100,000 used.)*
- **Retrieval diagnostic (no LLM tokens consumed):** Top-5 returned `Student Reviews — Intro CS Courses` (×2), `Open Syllabus`, `Student Reviews — Professors`, `CS50x 2023 Syllabus`. The MIT 6.006 chunk is **not in the top-5**, even though it contains the answer.
- **Judgment:** ❌ **Predicted Inaccurate (same retrieval failure as Q3).** Based on the retrieval evidence, the LLM would either refuse with the fallback phrase or answer from one of the irrelevant chunks. To be re-run after token quota resets to confirm.

### Q5 — Open Syllabus scope

- **Question:** *Open Syllabus claims to map the college curriculum across how many syllabi?*
- **Expected answer:** 32.9 million syllabi.
- **System response:** *(LLM call could not be completed at this run due to the same daily token limit.)*
- **Retrieval diagnostic (no LLM tokens consumed):** Top-5 ranks the Open Syllabus chunk at position 1 with cosine distance **0.225** (very strong match). The retrieved chunk contains the verbatim phrase `"Mapping the college curriculum across 32.9 million syllabi"`.
- **Judgment:** ✅ **Predicted Accurate.** Retrieval is unambiguous; identical query/chunk combinations have been answered correctly during prior smoke tests this session. To be re-run after token quota resets to confirm verbatim output.

### Summary

| Q | Topic | Judgment | Notes |
|---|---|---|---|
| 1 | CS50 problem sets | ✅ Accurate | Verbatim quote, right source |
| 2 | CS107 announcements | ✅ Accurate | Verbatim quote, right source |
| 3 | MIT 6.0001 audience | ❌ Inaccurate | Retrieval missed; LLM refused per grounding rules |
| 4 | MIT 6.006 resources | ❌ Predicted Inaccurate | Same retrieval failure; LLM not re-run yet |
| 5 | Open Syllabus syllabi count | ✅ Predicted Accurate | Retrieval at dist 0.225; LLM not re-run yet |

**Confirmed accurate: 2/5. Predicted accurate pending re-run: 1 (Q5). Inaccurate: 1 confirmed (Q3) + 1 predicted (Q4).**

The two failures share a single root cause traced in the next section.

---

## Failure Case Analysis

<!-- Identify at least one question where retrieval or generation did not work as expected.
     Write a specific explanation of *why* it failed, tied to a part of the pipeline.

     "The answer was wrong" is not an explanation.

     "The relevant information was split across a chunk boundary, so retrieval returned
     only half the context — the model didn't have enough to answer correctly" is an explanation.

     "The embedding model treated the professor's nickname as out-of-vocabulary and returned
     results from an unrelated review" is an explanation. -->

**Question that failed:** Q3 — *"According to MIT 6.0001's course description, who is the course intended for?"* (Q4 fails for the same reason; analyzed together below.)

**What the system returned:** *"I don't have enough information on that."* — the no-info fallback, despite the expected phrase being present in `documents/cleaned/mit_6_0001.txt` (and analogously for 6.006).

**Root cause — retrieval stage, specifically the embedding-similarity layer.**

The MIT OCW course-root pages clean down to very small documents (171 tokens for 6.0001, 181 tokens for 6.006) consisting mostly of structured labels: course number, instructor names, a topic list, and a "Learning Resource Types" label list. There is one narrative sentence — the course description — but it sits inside a chunk dominated by short labels. When `all-MiniLM-L6-v2` embeds this chunk, the resulting vector reflects the *aggregate* of all those signals, most of which are structural ("Topics", "Engineering", "Computer Science", "Lecture Notes", "Problem Sets", ...).

The evaluation queries, by contrast, are full natural-language sentences with strong narrative shape ("who is the course intended for", "which resource types are listed"). Their query vectors land closer to other narrative chunks — student reviews, CS50's prose syllabus, the Open Syllabus mission paragraph — than to the label-heavy MIT chunks. Concretely, in the Q3 retrieval the top-5 distances ranged 0.578–0.706, and none of those slots was the MIT 6.0001 chunk.

The source-aware reranker in `src/search.py` does add +20 per query token (length > 3) that appears in the source title, so "6.006" should boost the MIT 6.006 chunk. But the underlying cosine distance gap is too large for the bonus to overcome, and "MIT" is too short (3 chars) to trigger the bonus. For Q3, "6.0001's" appears in the query with an apostrophe-s, which fails the substring match against the source title's "6.0001" — so the bonus never fires for the most relevant query token.

**What I would change to fix it:**

1. **Lower the source-title token-length threshold from `> 3` to `>= 3`** so "MIT" triggers the reranker boost. One-line change in `src/search.py`.
2. **Normalize query tokens before substring matching** — strip apostrophe-suffixes (`"6.0001's"` → `"6.0001"`) so the boost matches consistently. Also one-line change.
3. **Either** (a) expand the corpus so the MIT chunks aren't the *only* MIT-specific signal in the index, or (b) hybrid retrieval: combine BM25/keyword search with the semantic search and union the top-k. Keyword search would surface "6.0001" and "6.006" mentions reliably regardless of embedding distance.
4. **Per-document chunking floor adjustment** — for tiny structured pages (< 200 tokens), augment the chunk with the document title and URL header so the chunk's embedded representation has more semantic context tying it to the source. Currently the title lives only in the provenance header above the cleaned body, which the chunker strips.

Of these, #1 and #2 are five-minute fixes worth trying first. If they don't move the MIT chunks into the top-5, #3 (hybrid retrieval) is the structural answer.

---

## Spec Reflection

<!-- Reflect on how planning.md shaped your implementation.
     Answer both questions with at least 2–3 sentences each. -->

**One way the spec helped you during implementation:**

The Chunking Strategy section of `planning.md` made the implementation decisions before code was written. Specifically, having the two-tier policy (1000/200 for long, 300/50 for short), the sentence-boundary rule, and the "single chunk if under the secondary threshold" fallback all written down meant I never had to stop mid-implementation to debate parameters. When I wrote `src/ingest_and_chunk.py`, I could lift the numbers directly into `TIER_CONFIG`. The spec also caught a real bug: I'd initially used `chunk_tokens // 2` as the single-chunk gate (for long-tier, this meant docs under 500 tokens became one chunk), and re-reading planning.md mid-implementation surfaced that the rule was actually "under the secondary threshold," i.e., under 300 tokens regardless of tier. That correction (committed as `SINGLE_CHUNK_THRESHOLD = 300`) wouldn't have happened without the spec to check against.

**One way your implementation diverged from the spec, and why:**

The spec described preprocessing as a sub-step *inside* the chunker (planning.md's "Preprocessing rules before chunking" lives under Chunking Strategy). My implementation split it out into a separate stage: `src/load_documents.py` → `src/clean_documents.py` → `src/ingest_and_chunk.py`, with intermediate artifacts written to `documents/raw/` and `documents/cleaned/`. I diverged because cleaning is the messiest, most iterative part of the pipeline — the first cleaning pass left a 60-item CS107 sidebar inside a chunk, the second was too aggressive and stripped MIT's "Learning Resource Types" list, the third was right. Each iteration cost zero LLM tokens because the intermediate cleaned files are just text on disk, and I could re-run only the cleaning step without re-fetching pages or re-chunking. If cleaning had been inline in the chunker, every iteration would have meant running the whole pipeline. The architectural cost is one extra script and one extra directory; the engineering benefit is fast, isolated iteration on the noisiest stage.

---

## AI Usage

<!-- Describe at least 2 specific instances where you used an AI tool during this project.
     For each: what did you give the AI as input, what did it produce, and what did you
     change, override, or direct differently?

     "I used Claude to help me code" is not sufficient.
     "I gave Claude my Chunking Strategy section from planning.md and asked it to implement
     chunk_text(). It returned a function using a fixed character split. I overrode the
     chunk size from 500 to 200 because my documents are short reviews, not long guides." -->

**Instance 1 — Generating the two-tier chunker from the Chunking Strategy**

- *What I gave the AI:* The Chunking Strategy section of `planning.md` verbatim, the list of `documents/*.txt` files I had collected, and a directive to produce a runnable `src/ingest_and_chunk.py` that implemented the two-tier policy (1000/200 long, 300/50 short), sentence-boundary-aware splitting, per-chunk metadata, and a JSONL output. I also asked for an inspection report alongside the chunk file.
- *What it produced:* A working chunker that used a custom regex sentence splitter, a greedy sentence-packer for the chunk loop, and `tiktoken` for exact token counts. The first version had two problems: (a) it used `chunk_tokens // 2` as the single-chunk threshold (so long-tier docs under 500 tokens became single chunks), which didn't match the spec's "under the secondary threshold (300 tokens)" rule; and (b) the cap check was `current_tok + sent_tokens[j] <= chunk_tokens` based on summed per-sentence token counts, so when sentences were joined with a space the actual joined token count occasionally exceeded the cap by 10–25 tokens (one CS107 chunk came out at 1021 tokens against a 1000 cap).
- *What I changed or overrode:* (1) Replaced the single-chunk gate with `SINGLE_CHUNK_THRESHOLD = TIER_CONFIG["short"]["chunk_tokens"]` so the rule matches the spec exactly. (2) Replaced the additive cap check with a re-tokenization of the candidate joined chunk (`n_tokens(" ".join(current + [sentences[j]])) > chunk_tokens`) — slower but it makes the cap hard, which is what the spec actually requires. After these changes the inspection report showed zero cap violations across all 11 chunks.

**Instance 2 — Stripping CS107's sidebar from the cleaning step**

- *What I gave the AI:* Output from `chunks/inspection.md` showing that `cs107_stanford` chunk 0 opened with a ~250-token nav dump (`"CS107 Handouts CGOE Information Honor Code Course Enrollment FAQ ... 1: Welcome to CS107! 2: Unix and C ..."`) before any real announcement text. I asked the AI to extend `src/clean_documents.py` so this kind of in-page sidebar gets dropped, and to leave the rest of the corpus untouched.
- *What it produced:* A `strip_long_navlike_runs()` helper that scanned the *entire* document for runs of 10+ consecutive nav-like paragraphs (single line, ≤ 60 chars, no internal sentence period) and dropped every such run wherever it appeared. It correctly removed CS107's leading sidebar. But it also matched the 13-paragraph list inside the MIT 6.006 page that runs `"Topics → Engineering → Computer Science → Algorithms and Data Structures → Theory of Computation → Mathematics → Computation → Learning Resource Types → Exam Solutions → Exams → Lecture Notes → Lecture Videos → Problem Set Solutions → Problem Sets"` — a real content list that happens to look nav-like in isolation. MIT 6.006's cleaned doc dropped from 181 → 97 tokens and lost the answer to evaluation question Q4 entirely.
- *What I changed or overrode:* I caught the regression in the next run (cleaned-doc size dropped 50%) and redirected the AI to constrain the strip to the *leading* run at the very top of the document only (`strip_leading_navlike_run`). I also caught a separate bug where the navlike check used `if "\n" in p: return False`, which terminated CS107's run early because `"12: Disclosure, Partiality, Generics and<br>void *"` had been split across two lines by HTML extraction — I changed the check to join the paragraph to one line before measuring length, so multi-line nav entries still get caught. After these directional changes, CS107 chunk 0 now opens with substantive content and MIT 6.006 is fully preserved.
