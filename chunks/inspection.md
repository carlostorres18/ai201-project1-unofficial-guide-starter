# Chunk Inspection Report

Total chunks: **11**

Sources: **7**


## Per-source summary

| Source | Tier | Chunks | Avg tokens | Min | Max | Cap |
|---|---|---|---|---|---|---|
| cs107_stanford | long | 4 | 860 | 474 | 999 | 1000 |
| cs50_syllabus | long | 1 | 970 | 970 | 970 | 1000 |
| mit_6_0001 | long | 1 | 171 | 171 | 171 | 1000 |
| mit_6_006 | long | 1 | 181 | 181 | 181 | 1000 |
| open_syllabus | long | 1 | 156 | 156 | 156 | 1000 |
| reviews_intro_cs_sample | short | 2 | 201 | 105 | 298 | 300 |
| reviews_professors_sample | short | 1 | 183 | 183 | 183 | 300 |

## Token cap violations: 0


## Sentence boundary spot check (5 random chunks)

### mit_6_006 chunk 0 (181 tok)
- starts: `Undergraduate  6.006 | Spring 2020 | Undergraduate  Introduction to Algorithms  Quizzes  Practice Problems  Course Descr…`
- ends:   `…f. Demaine demonstrates how he uses algorithms to create intricate origami figures. (Image courtesy of the instructors.)`

### reviews_professors_sample chunk 0 (183 tok)
- starts: `# Student Reviews — Professors (manually collected samples)  Source type: short professor reviews paraphrased/anonymized…`
- ends:   `…he secret weapon for these intro courses. Going once a week made the difference between drowning and thriving in CS107."`

### cs107_stanford chunk 0 (978 tok)
- starts: `Important course announcements will be posted below and announced in class and on the Ed Discussion forum. You are respo…`
- ends:   `…n CEMEX Auditorium. Please see the midterm exam webpage for information about the exam, review materials and study tips.`

### cs50_syllabus chunk 0 (970 tok)
- starts: `This is CS50x 2023, an older version of the course. See cs50.harvard.edu/x/2024 for the latest! David J. Malan malan@har…`
- ends:   `…must submit (and receive a score of at least 70% on) it by 31 December 2023. Please see Academic Honesty for guidelines.`

### open_syllabus chunk 0 (156 tok)
- starts: `Mapping the college curriculum across 32.9 million syllabi. Open Syllabus is a massive non-profit archive of the main ac…`
- ends:   `…nts of the top-assigned titles in 11 fields, grouped into beautiful galaxies.  News and data stories from Open Syllabus.`


## Overlap verification

Adjacent chunks in the same source should share trailing/leading text.

| Source | Pair | Shared chars (≥) |
|---|---|---|
| cs107_stanford | 0->1 | 856 |
| cs107_stanford | 1->2 | 946 |
| cs107_stanford | 2->3 | 908 |
| reviews_intro_cs_sample | 0->1 | 292 |