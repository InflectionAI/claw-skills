---
name: dbcd
version: 1.0.0
description: |
  SaaSpocalypse Survival Scanner. Analyze any SaaS company and generate a humorous
  "Death Report" scoring how likely it is to be replaced by a Claude Skill (.md file).
  Use when: "saas scanner", "death report", "saaspocalypse", "can a skill replace this",
  "roast this SaaS".
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Write
  - Agent
  - WebSearch
  - WebFetch
  - AskUserQuestion
---

# SKILL: SaaSpocalypse Survival Scanner

## Purpose
Analyze any SaaS company and generate a humorous "Death Report" scoring how likely it is to be replaced by a Claude Skill (.md file).

## Instructions
1. Accept a company URL from the user
2. Research the company's product, pricing, features, and market position
3. Evaluate their defensibility against AI replacement
4. Score them on CRUD complexity, AI wrapper likelihood, moat depth, markdown replaceability, and pricing audacity
5. Generate a devastating but funny roast report
6. Include a plausible SKILL.md that could replace their core product
7. Write a eulogy, cause of death, and fictional last words
8. Format as structured JSON

## Scoring Rubric
- 0-10: IMMORTAL (hardware, deep science)
- 11-25: SAFE (strong moat)
- 26-45: SWEATING (Claude is closing in)
- 46-65: CRITICAL (clock is ticking)
- 66-85: FLATLINING (investors panicking)
- 86-100: ALREADY DEAD (literally a .md file)

## Tone
Roast comedy meets funeral speech. Be specific, be funny, be merciless.

## Output
Return structured JSON with deathScore, eulogy, skillMdFile, and all metrics.
