# PRD: Module 5 Section 3 (aligning the LLM-as-judge on the deep agent)

Status: Draft for review (2026-11-12). Owner: Ariel Herrera. Branch: `feat/module-5-evals-201`.

## 1. Goal

Sections 1 and 2 rested every decision on one number: the `correctness` score from the LLM-as-judge. Section 3 checks whether that judge agrees with a person **on the deep agent's answers**, finds where it's wrong, and fixes its rubric one cause at a time, the way `module_2/bonus_align_llm_judge.ipynb` does for the supervisor agent.

It also produces the two things Section 4 (Jev as a judge) needs: a human-labeled golden set of deep-agent outputs and an aligned judge prompt to compare Jev against.

## 2. Principles

Same as Sections 1–2 (`docs/2026-11-12-module-5-sections-1-2-prd.md` §2): mirror the Module 2 notebook, change only what the different agent requires, list every deviation with its reason, and don't compare to Module 2 inside the notebook.

## 3. Why the deep agent needs its own alignment

The Module 2 golden set and rubric were built for the supervisor agent. The deep agent's answers differ in ways the judge has to handle, and Sections 1–2 already showed disagreements:

| Deep-agent behavior | Seen in | Why the Module 2 rubric may misjudge it |
|---|---|---|
| Masks PII the customer asked for: "***-***-0234 … For privacy, I can only share it in masked form" | Section 2, phone-number and account-type answers | The rubric has no rule for privacy masking; whether it's correct is a labeling decision (§7 Q3) |
| Offers actions it can't take: "I can help with updating it" | Sections 1 and 2, the same two answers | Module 2's `fabricated` failure; the Module 2 rubric's "additional information" note lets it pass |
| States something it never checked: "There's no phone number on file" | Section 1 (rigid tools can't read the customer record) | Sounds definitive; only the reference shows it's wrong |
| Can actually **request** a refund (`request_refund`, paused for approval) | Agent design | Module 2's rule "the assistant can only look up…" would wrongly fail a legitimate refund offer, and must still fail "your refund has been issued" |
| Long, sourced answers ("per our Return Policy…", breakdowns, next steps) | Laptop return-policy answer flipped between runs | Extra detail and recited policy are the Module 2 `fabricated` / `recited` territory, with different wording |
| Meta statements ("I used the verified account on file, not the email typed in chat") | Section 1 single-example output | Neither right nor wrong under the current rubric |
| Stops early when the order specialist hits its tool-call limit (15) | Section 1: six examples at 14–15 calls | Partial answers that sound complete |
| Refuses cross-customer requests | The authorization example | A correct refusal must be judged correct |

## 4. Notebook outline: `section_3_align_llm_judge.ipynb`

Mirror of `module_2/bonus_align_llm_judge.ipynb` (34 cells).

| # | Module 2 step | Module 5 step | Visual | Code |
|---|---|---|---|---|
| 0 | Title, "what is an aligned judge", step table | Same, about the judge from Sections 1–2 | Step table | — |
| 0b | `align-evals-workflow.png` | Same image, unchanged (agent-neutral) | `images/align-evals-workflow.png` | — |
| S | Setup; pin `JUDGE_MODEL` with the "measuring instrument" note | Same | — | Imports, `load_dotenv()` before workshop imports, warning filters |
| 1 | Load the golden set: 30 items, how they were made, bucket table, read 3 `label_note`s | Same, for `module_5/golden_set.json` (see §6), with the deep-agent buckets | Bucket table | Load, count labels and buckets, print three notes |
| 1-sec | 🔒 Production security note (scrub before labeling and judging) | Same, plus: the deep agent's own PII redaction doesn't make a golden set safe to share | — | — |
| 1.1 | Create the dataset in LangSmith (idempotent) | Same, dataset `techhub-deep-agent-judge-alignment` | — | Same code |
| 1.2 | Target function returns the frozen output | Same | — | Same code |
| 2 | Measure the Module 2 judge (`make_judge`, `matches_human`, `report`, v0 run) | Measure the **Sections 1–2 judge** (same `CORRECTNESS_PROMPT`) | Agreement + confusion matrix printout | Same code |
| 2.1 | Analyze results: failure patterns, table of the causes found | Same, with the causes found in T6 | Cause table | — |
| 3 | Fix the rubric, one cause at a time (3.1 invented actions, 3.2 explicit answer) | Same method; one subsection per cause found in T6 (expected candidates in §3) | — | One `PROMPT_Vn` per fix, each asserting its `replace()` matched |
| 3.3 | Compare the versions (bar printout), compare in UI, check remaining disagreements, overfitting note, nondeterminism note | Same | Agreement bars | Same code |
| 4 | Optional: label the outputs yourself (annotation queue) | Same | — | Same code, queue `techhub-deep-agent-judge-alignment-labels` |
| 5 | Use the aligned judge; Align Evaluator in the UI with three GIFs | Same, pointing at where the aligned prompt lives (§8 D5) | Same GIF table | `print(PROMPT_FINAL)` |

## 5. Deviations from Module 2

| # | Deviation | Why |
|---|---|---|
| D1 | New golden set from deep-agent outputs (`module_5/golden_set.json`), same schema | The judge must be aligned on the outputs it will grade |
| D2 | Outputs come mostly from the real Section 1 and 2 experiments, with edited copies only for buckets with no natural example | The rigid and SQL runs already contain both correct and incorrect answers (cut-off chains, masking, flips); Module 2 needed 16 edits because its runs were mostly correct |
| D3 | Different and extra buckets (§6) | The deep agent fails differently (masking, early stops, refusals) |
| D4 | The "actions the assistant can take" rule lists `request_refund` (pending approval) | The deep agent can request refunds; Module 2's agent couldn't |
| D5 | The final aligned prompt is saved in `evaluators/` (proposed) | Section 4 compares Jev against it. Module 2 kept its aligned prompt in the notebook (a shared version was reverted in `99cda86`) |

## 6. Golden set

Schema, same as Module 2: `id`, `bucket`, `question`, `reference`, `output`, `human_label`, `label_note`, `source`.

- **Sources:** the 26 final answers from the clean Section 1 (`deep-agent-baseline-6d90ce6d`) and Section 2 (`deep-agent-sql-3c01a2ba`) experiments, frozen. `source` records the experiment and run ID. Plus up to about 8 edited copies for buckets with no natural example, each edit introducing or fixing exactly one mistake (as Module 2 does). Target: about 30–34 items with both labels in most buckets.
- **Buckets** (to finalize during labeling):

| Bucket | Label | What the output does |
|---|---|---|
| `ok` | correct | Answers accurately |
| `refused` | correct | Correctly declines another customer's data |
| `numbers` | incorrect | Wrong count, price, or total, or a missing order |
| `cut_off` | incorrect | Stops partway (tool-call limit) but reads as complete |
| `fabricated` | incorrect | Claims or offers something the agent can't do or didn't do (e.g. "your refund has been issued") |
| `recited` | incorrect | Recites policy without answering the customer's question |
| `masked` | per §7 Q3 | Hides data the verified customer asked for |
| `wrong` / `no_answer` | incorrect | Wrong answer, or no answer |

- **Labels are the standard the judge is aligned to.** Every label is Ariel's call (§7 Q2).

## 7. Decisions

| # | Question | Proposed | Status |
|---|---|---|---|
| Q1 | Golden-set source: real Section 1–2 outputs plus a few edits (D2), or Module 2's recipe (about 14 raw + 16 edited)? | Real outputs plus edits | Decided 2026-11-12 |
| Q2 | Labeling: Claude drafts every label, bucket, and note, flagging uncertain ones, and Ariel reviews all of them (in a LangSmith annotation queue or a review table); or Ariel labels from scratch? | Draft + full review; nothing is final until Ariel approves it | Decided 2026-11-12 |
| Q3 | Policy calls for labeling: is masking the phone number the verified customer asked for correct? Are meta statements ("I used the verified account on file") fine? | Masking: incorrect (the customer is verified and asked for their own data). Meta statements: fine | Decided 2026-11-12 (as proposed) |
| Q4 | Judge model: pin `openai:gpt-5-mini` like Module 2, or the model Sections 1–2 used (`DEFAULT_MODEL`)? | Pin like Module 2, and say so | Decided 2026-11-12 |
| Q5 | Save the final prompt in `evaluators/` (D5)? | Yes, as `DEEP_AGENT_CORRECTNESS_PROMPT` plus an evaluator, for Section 4 | Decided 2026-11-12 |

## 8. Tasks

Each task ends with a commit. Check items off here as they land.

**Golden set**
- [x] **T1** Export the 26 final answers (question, reference, output, experiment and run ID) from the two clean experiments into a candidates file. Check that none of those runs errored.
- [x] **T2** Draft a bucket, label, and `label_note` for each candidate, flagging uncertain ones. Add edited copies for buckets with no natural example.
- [x] **T3** **Ariel reviews every label** (per Q2) and settles the policy calls (Q3). Write `workshop_modules/module_5/golden_set.json`. **Approved by Ariel 2026-11-12 (33 items: 26 real, 7 edited; 18 correct, 15 incorrect); review doc: `docs/2026-11-12-module-5-golden-set-review.md`.**

**Measure and fix**
- [x] **T4** Spike: run the v0 judge (the Sections 1–2 `CORRECTNESS_PROMPT`, pinned model) on the golden set 3 times. Record agreement, the confusion matrix, and every disagreement grouped by cause. Record the causes in §10.
- [x] **T5** For each cause, write one rubric rule, re-measure 3 times, and keep it only if it fixes its cause without breaking another bucket. Record each version's agreement in §10.
- [x] **T6** Hold-out check: before T5, set aside about 5 labeled items that the rules are not written against, and report agreement on them separately (addresses Module 2's overfitting warning).

**Code and notebook**
- [x] **T7** Save the final prompt and evaluator in `evaluators/` (per Q5), with a unit test that the prompt formats and that each rule's `replace()` target exists.
- [ ] **T8** Add `s3` to `build_module5.py` and generate `section_3_align_llm_judge.ipynb` per §4. The analysis tables in 2.1 and 3.x use the causes and wording from T4–T5.

**Validate and document**
- [ ] **T9** Run the notebook end to end from a fresh kernel. Check every experiment for run errors before reading scores. Confirm the agreement numbers match §10 within run-to-run variance.
- [ ] **T10** Docs: `workshop_modules/README.md` Section 3 entry, `CLAUDE.md` Module 5 notes, project memory.

## 9. Acceptance criteria

- Headings and order match `module_2/bonus_align_llm_judge.ipynb`, except the per-cause subsections in §3, whose number and names come from the data.
- Every golden-set label has been reviewed by Ariel.
- The final prompt beats v0 on agreement, averaged over 3 runs, and doesn't do worse on the hold-out items.
- Every experiment the notebook creates has zero run errors.
- The notebook runs top to bottom in a fresh kernel.
- `tests/` pass.

## 10. Results (T4–T6 spike, 2026-11-12; judge `openai:gpt-5-mini`; each row is 3 runs over 33 items)

Hold-out (chosen before measuring, never used to write rules): `sql-4`, `rigid-13`, `rigid-3`, `sql-9`, `sql-10`, `edit-sql-2-account-updated`.

| Version | All | Rubric items (27) | Hold-out (6) | Notes |
|---|---|---|---|---|
| v0 (Sections 1–2 judge) | 93% | 96% | 78% | Passes invented actions as "acceptable extras" (`edit-sql-7-refund-issued` 3/3; hold-out `edit-sql-2-account-updated` 3/3); hold-out masking 1/3 |
| v1 (Module 2's full Fix 1: rule + "read every offer" + looser note) | 87% | 86% | 89% | Fixes invented actions but turns lenient: passes cut-off, partial, and masked answers ("no disallowed claims, so it is correct") |
| v1a (the action rule only) | 90% | 90% | 89% | Same leniency, less of it. Kept as Fix 1 |
| v1b (rule + "read every offer") | 86% | 88% | 78% | Worse |
| v2 draft (+ answer what was asked, unscoped) | 96% | 96% | 94% | Over-reaches: fails good answers for not repeating the customer's account details |
| v3 (+ "reference facts are true") | 92% | 90% | 100% | Doesn't fix its target, adds noise. Dropped |
| **v2 (v1a + answer what was asked, scoped)** | **97%** | **96%** | **100%** | One disagreement left, 3/3: `edit-sql-1-breakdown-fixed`, where the judge says mice aren't keyboards (the catalog files them under Keyboards) |

Causes, for §2.1: (1) invented actions pass as extras, from the "additional information" note; (2) after an action rule, the judge treats "no disallowed claims" as the bar and passes honest non-answers ("couldn't verify stock") and masking; (3) the judge overrides the reference with world knowledge (the mice). Fix 1 addresses (1); Fix 2 addresses (2); (3) is left as the "judge or label?" discussion in §3.3.

## 11. Risks

- **Label bias.** If Claude's draft labels are accepted without real review, the judge gets aligned to Claude, not to TechHub's standard. T3 is a blocking human step for this reason.
- **Overfitting.** About 30 items find failure modes; they don't certify a judge. The hold-out (T6) and Module 2's "add labels before calling it done" note cover this.
- **Nondeterminism.** The judge can move by an item or two between runs; compare versions on repeated runs.
- **The golden set reflects one run of each agent.** If the agent changes a lot (new tools), re-export and relabel.

## 12. Out of scope

- Section 4 (Jev), beyond producing the golden set and prompt it uses.
- The Module 2 "review the judge in a Custom App" bonus (on an unmerged branch).
- Changing the judge used by Sections 1–2. They keep the unaligned prompt, which is the point of Section 3.
