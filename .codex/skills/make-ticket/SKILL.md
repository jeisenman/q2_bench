---
name: make-ticket
description: Create Jira tickets from a user request when the destination board, project, and Atlassian site must be explicit and verified.
metadata:
  short-description: Create a Jira ticket on an explicit board
---

# Make Ticket

Use this skill when the user asks to create, make, or file a Jira ticket.

## Destination is required

Before any Jira write, require an explicit destination board:

- Accept a board URL such as `https://site.atlassian.net/jira/software/c/projects/RA/boards/5705`.
- Also accept explicit site hostname, project key, and board ID when no URL is provided.
- Parse and retain the exact site hostname, project key, and board ID. Treat them as authoritative.
- Do not infer a board from the current browser tab, a prior issue, an accessible sandbox, or the user's team.
- If the board is missing or ambiguous, ask for the board URL and stop before creating anything.

Verify the exact destination site with `getAccessibleAtlassianResources`. If it is not authorized, stop and tell the user which site must be connected. Never create the ticket on another accessible site as a fallback.

Use `getVisibleJiraProjects` with the destination site and project key to verify that the project exists and is writable. Inspect the project's issue types and fields before choosing a ticket type or setting custom fields.

## Match the board's conventions

After destination verification:

1. Search the destination project and board's current work for comparable maintenance tickets.
2. Reuse the matching issue type, parent, sprint, story-point field, labels, and project-specific fields only when the user requests the same pattern or the evidence clearly establishes it.
3. A board is not itself a Jira issue field. If the user asks for the current sprint or placement on the board, resolve the board's active sprint and set the sprint field explicitly.
4. Do not claim that a ticket is on the requested board unless a post-create readback confirms the destination project and the board/sprint relationship.

Use Rovo Teamwork Graph context for relationships among issues, people, sprints, repositories, and pull requests when needed. Use ordinary Jira tools for issue search, creation, field updates, assignment, comments, and transitions.

## Create and verify

Create exactly one issue unless the user explicitly requests multiple tickets. Preserve the user's scope and wording while adding concise acceptance criteria when useful.

Apply requested values for:

- summary and description;
- issue type and parent;
- assignee;
- story points;
- sprint;
- labels and project-specific fields;
- workflow status.

After creation, read the issue back and verify the summary, project key, board/sprint placement, parent, assignee, points, and status. If a workflow requires intermediate transitions, use the available transitions in order and verify the final status.

If creation succeeds on the wrong site or project, do not delete or silently recreate it. Report the mismatch and ask before taking corrective action.

## Final response

Return the issue key and a link to the issue, followed by the verified destination board, project, sprint, assignee, points, and status. If anything could not be verified, state that explicitly.
