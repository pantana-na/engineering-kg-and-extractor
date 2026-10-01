load("//learning/gemini/agents/skill_rules:skills.bzl", "agent_skill")
load("//learning/gemini/agents/skills/skill_creator/scripts:skill_defs.bzl", "validate_skill_test")

package(default_visibility = ["//learning/gemini/agents/skills:__subpackages__"])

agent_skill(
    name = "architecture_diagram",
    srcs = [
        "SKILL.md",
        "resources/template.html",
    ],
)

validate_skill_test(
    name = "validate_architecture_diagram_skill_test",
)
