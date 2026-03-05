# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.1.0] - 2026-03-04

### Added
- Seamless onboarding & setup experience (US-011): single-command CLI wizard (`python -m research_agent setup`), Qdrant local mode as default, UI first-run onboarding flow (entity mapping → connect → board/field mapping → sync → first query), vector count monitoring with limit enforcement, `doctor` and `reindex` commands.
- Onboarding field mapping UX: one Map fields step per entity (dynamic wizard steps), semantic + deterministic column suggestions with Product OS field descriptions, loading overlay and preload for all entities to avoid lag.

### Changed
- Field mapping suggestions now replace (not merge with) defaults so dropdowns show correct Monday.com columns.
