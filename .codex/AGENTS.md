# Codex CheckPoint Project Archiving

All user-facing knowledge notes belong in the configured Obsidian vault. Independent work uses exactly one file at `项目总结/<项目名>.md`. Do not create a project directory or additional project-note files for an independent project.

When the user asks to archive a task under an existing project or parent project, ask this exact question before writing: “该项目是否归属于‘<父项目>’？” Create `项目总结/<父项目>/` only after an explicit confirmation. The parent summary is `项目总结/<父项目>/项目总结.md` and must include `group_confirmed: true` plus its `children` list in frontmatter.

When projects do not have a confirmed parent-child relationship, merge their current-session summary into one flat project note and preserve every participating session identifier in the `session_ids` frontmatter field. Do not infer the hierarchy from names, folders, tags, or previous summaries.

The `synthesize` skill always writes `项目总结/<项目名>.md` and marks its source sessions and project summary as knowledge-archived. It measures the selected sessions by recorded user-message count and material length. A long session requires a user question before any long-term experience is written; a short session must state that no long-term experience was written and that the project summary was archived. The user may explicitly force long-term extraction.

AI development reference is user-controlled core knowledge. Create or replace `AI开发参考/<项目名>.md` only through the `synthesize` skill after the user explicitly authorizes it. Before writing, assess whether the material contains at least three independently useful categories among verified conclusions, code or configuration, executable commands, operating methods, validation evidence, and pitfalls. When the material is insufficient, ask whether the user still requires the summary; do not write it without the answer. Existing AI development references must never be deleted, replaced, or downgraded by automatic hooks. Keep one file per project and do not create indexes or subdirectories.

Metadata enrichment may add `aliases` and `keywords` to checkpoints, project summaries, and user-authorized AI development references. Existing user-authored metadata must be preserved. Metadata enrichment must never create, replace, delete, or authorize an AI development reference.

When a relevant AI development reference is reused in a new task or another project, tell the user at the beginning of the reply which document is being reused. Reuse requires a direct project or alias match, or at least two specific feature terms; broad topic terms alone must not trigger it. The document can then be used as compact context.

Automatic checkpoint writes must produce a user-visible Stop-hook notification only after `Session checkpoint written` is present. The notification must state the vault-relative checkpoint file and its parent directory. When the note remains in `Codex工作记录/会话断点/未分类对话/`, it must also state that the checkpoint is unclassified and direct the user to `$checkpoint` for classification. Manual classification must process only this directory and the current manually rechecked session; existing categorized sessions remain untouched.
