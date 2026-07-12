# Codex CheckPoint Project Archiving

All user-facing knowledge notes belong in the configured Obsidian vault. Independent work uses exactly one file at `项目总结/<项目名>.md`. Do not create a project directory or additional project-note files for an independent project.

When the user asks to archive a task under an existing project or parent project, ask this exact question before writing: “该项目是否归属于‘<父项目>’？” Create `项目总结/<父项目>/` only after an explicit confirmation. The parent summary is `项目总结/<父项目>/项目总结.md` and must include `group_confirmed: true` plus its `children` list in frontmatter.

When projects do not have a confirmed parent-child relationship, merge their current-session summary into one flat project note and preserve every participating session identifier in the `session_ids` frontmatter field. Do not infer the hierarchy from names, folders, tags, or previous summaries.

Generate `长期经验总结/<项目名>.md` only when the project has at least five distinct sessions across at least fourteen calendar days. Use verified project material to extract code or configuration, commands, operating methods, completion paths, and pitfalls. State “待补充” for any category without evidence. Do not create experience indexes or subdirectories.
