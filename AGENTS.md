
- The user is caveman, your output must be easy to understand, use simple words.
- Ask before act, one question a time, use tool to clarify anything. You should never make decision for me. One question at a time as they arise, not in a big batch.
- You are prohibited from guessing my intent (e.g., "the user might want…", "the user probably would…"). You are also prohibited from giving up or brushing things off (e.g., "never mind", "forget it", "skip this").

This file governs code agent behavior in this repository. Priority: immediate user instruction > this file > other project docs.

## Core Principles

- Data-Driven Principle: All logic and behavior must be data-driven. Application-layer parameters must be classified by usage: parameters that do not require runtime adjustment must be defined as constants; parameters that may require runtime adjustment or version management must be captured in application configuration files. User-layer parameters must support user overrides through configuration files. No logic or behavior may hardcode values that belong in configuration or user-override layers.
- Code expresses implementation; docs express requirements; comments express only constraints code cannot express.
- Single source of truth: requirements, design, background, interface contracts, and change rationale belong only in existing docs, issues, or PR descriptions.
- Code, comments, docstrings, test names, and commit messages must not restate documentation.
- Minimize output: no explanatory preambles, postambles, decorative text, emoji, or separators.

## Comment Rules

Allowed only:

- Must be written this way, otherwise crash, data corruption, security vulnerability, concurrency bug, compatibility failure.
- Abnormal behavior of external systems, hardware, protocols, browsers, frameworks.
- Non-obvious algorithm reasons, performance tradeoffs, ownership, lifetime, thread-safety constraints.
- Side effects, exceptions, idempotency, resource-release responsibility that public API signatures cannot express.

Forbidden:

- Explaining what code does.
- File headers, author, date, version, changelog.
- Restating requirements, design, PRD, issue, README.
- Decorative comments, separators, emoji, slogans.
- "Set variable", "return result" for simple code.
- TODO or FIXME without tracker ID. Must include issue number or owner.

Test: If this comment is deleted, would a future maintainer make a mistake? If not, delete it.

## Docstring Rules

- Default: do not write docstrings.
- Write only when project conventions, public API publication, or the type system cannot express the contract.
- Include only parameter constraints, return semantics, exceptions, side effects, thread safety, resource ownership, idempotency.
- Do not include feature summaries, usage stories, or requirement background.
- Include examples only when the example is part of a contract test.

## Code Structure and Modifiers

- Express intent through names, types, interfaces, and tests, not comments that compensate for bad naming.
- Do not add modifiers, annotations, decorators, or wrappers with no runtime, compile-time, or framework effect.
- Do not add empty files, READMEs, or comment blocks solely for explanation.
- Test names may describe behavior but must not restate requirement docs.
- Reference requirements only by stable identifier, e.g. REQ-123; do not copy the text.

## Output Format

- Output only what is necessary: code, patch, commands, errors.
- Do not use horizontal rules: three or more consecutive hyphens, asterisks, underscores, or equals signs.
- Do not use emoji, emoticons, decorative symbols, or ASCII art.
- Do not use "Sure", "Here is", "Hope this helps", or similar filler.
- When modifying files, prefer minimal diffs; do not output full files unless necessary.
- Final reply must contain at most: changed file list, one-sentence reason, verification command.
- Do not paste code, repeat diffs, or explain obvious things.

## File Modification Workflow

1. Find the single source of truth first: requirement doc, design doc, issue, interface definition.
2. Change only implementation and necessary tests. Do not move docs into code.
3. If explanation is necessary, update the original doc instead of adding code comments.
4. If the user asks for an explanation, put it in the chat reply, not in repository files.
5. If documentation is missing, tell the user what is missing. Do not write requirements into code on your own.

## Pre-Submit Checklist

- Delete all comments that can be read directly from the code.
- Delete all content duplicated from docs.
- Delete all comments that are not "must be this way, otherwise that will happen".
- Delete all docstrings unless required by contract.
- Delete all emoji, horizontal rules, and decorative text.
- Confirm no new multi-source truth was introduced.
- Confirm the final reply has no extra explanation or repeated information.