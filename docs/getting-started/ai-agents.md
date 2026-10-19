# Use buildzr with AI agents

This guide shows how to give a coding agent, such as Claude Code, Cursor or Codex, the buildzr skill, so that it can model your architecture, build it and answer questions about it.

A **skill** is a folder of instructions that a coding agent reads when a task needs it. The buildzr skill lives in the `skills/buildzr` folder of the buildzr repository, next to the code it describes, so each release of buildzr comes with a skill that matches it.

## Before you start

You need:

- A coding agent that reads skills, in a project folder.
- Node.js on the machine, to run the [`skills`](https://github.com/vercel-labs/skills) command with `npx`. Version 1.7.2 of `skills` asks for Node.js 22.20 or newer.
- Python 3.10 or newer, and Node.js 18 or newer, for buildzr itself. The agent installs buildzr when it first needs it.

## Install the skill

In the folder of your project, run:

```bash
npx skills add amirulmenjeni/buildzr
```

The command finds the skill `buildzr`, asks which agents to install it for, and copies it into their folders, for example `.claude/skills/buildzr/` for Claude Code. To choose without questions, name the skill and the agent:

```bash
npx skills add amirulmenjeni/buildzr --skill buildzr --agent claude-code -y
```

To see what the repository offers without installing anything, add `--list`.

### Install from a local checkout

To try the skill of a branch, or to work without network access to GitHub, give the path of a buildzr checkout instead of `amirulmenjeni/buildzr`:

```bash
npx skills add ../buildzr --list
npx skills add ../buildzr --skill buildzr --agent claude-code -y
```

## What the agent can do with the skill

With the skill installed, the agent:

- installs buildzr and checks that its `buildzr` command has `build` and `serve`;
- writes model files in `workspaces/`: people, software systems, containers, components, relationships, groups, styles, and system landscape, system context, container, component, dynamic and deployment views;
- runs `buildzr build`, reads the errors of a broken workspace, fixes the model file and builds again until the build passes;
- starts `buildzr serve` and gives you the address of the viewer, or a link to one view or one element;
- answers questions about a served workspace from its [Model API](../model-api.md), such as "what depends on the database?", instead of reading the Python.

## Ask for a model

Give the agent a task in plain words. For example:

```text
Model an online shop with buildzr: customers, a web app, an API, a database and a
payment provider. Produce a system context view, a container view and a deployment
view, and build it.
```

Expect the agent to create `workspaces/<name>.py`, run `buildzr build` until it prints a `built .buildzr/build/<name> (...)` line and exits with code 0, and tell you how to open the result with `buildzr serve`. The viewer shows all three views; the deployment view draws the servers or cloud services as nested boxes with the containers that run on them. If a build fails, the agent sees the same `BROKEN` block as you do (see [When a workspace is broken](../serve-workspaces.md#8-when-a-workspace-is-broken)) and fixes the file.

## Next steps

- Let the agent, or any other program, query a served workspace: [The Model API](../model-api.md).
- Learn the commands the agent runs: [Command reference](../cli.md).
- Read what the agent writes: [Core Concepts](../user-guide/core-concepts.md) and [Views](../user-guide/views.md).
