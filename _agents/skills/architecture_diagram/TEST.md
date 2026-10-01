# Architecture Diagram Skill — Agent E2E Test Plan

## Prerequisites

**Read `SKILL.md` first** to understand the design system, double-rect masking
technique, legend placement rules, and expected output structure.

No custom CLI or external dependencies are required for this skill.

--------------------------------------------------------------------------------

## Test 1: Template reading and understanding

**Prompt:** "Create a high-level architecture diagram for a 3-tier web
application (Frontend, Backend API, PostgreSQL Database)."

**Verify:** - Agent reads `resources/template.html` using `view_file` to
understand the layout and design system. - Agent generates a markdown document and standalone `.html`
file adhering to the 4-part structure (Header, Main SVG, Summary Cards,
Footer). - Agent outputs the files using `write_to_file` in the `docs/` folder (e.g.,
`docs/3-tier-web-app-architecture.md` and `docs/3-tier-web-app-architecture.html`). - Agent provides instructions on how to
open the file in a browser (e.g., `xdg-open
./docs/3-tier-web-app-architecture.html`).

--------------------------------------------------------------------------------

## Test 2: Double-Rect Masking Technique

**Prompt:** "Draw an architecture diagram showing an API Gateway connecting to
an Auth Service and a Core Backend Service. Ensure connection arrows pass behind
the service boxes."

**Verify:** - Agent implements the **double-rect masking technique** for the
service components: 1. An opaque background rect (`fill="#0f172a"`). 2. A
semi-transparent styled rect on top matching the component type color palette. -
Arrows are drawn early in the SVG (after the grid) so they render behind the
service boxes. - Font size for primary component names is set to `12px`.

--------------------------------------------------------------------------------

## Test 3: Legend Placement and Boundary Boxes

**Prompt:** "Create a cloud infrastructure diagram for an AWS deployment in
us-east-1 containing a VPC boundary, public subnet, private subnet, and several
microservices."

**Verify:** - Agent creates dashed boundary boxes (`rx="12"`, amber/custom
color) representing the VPC and subnets. - Agent places the legend **outside all
boundary boxes** (calculating the lowest Y-coordinate of all boundaries and
placing the legend at least 20px below it). - SVG `viewBox` height is
appropriately sized (e.g., `820` or larger) to ensure the legend is fully
visible without clipping.

--------------------------------------------------------------------------------

## Test 4: Message Bus Placement

**Prompt:** "Visualize an event-driven architecture where an Order Service sends
events to a Kafka Message Bus, which are then consumed by an Inventory Service
and a Notification Service."

**Verify:** - Agent places the Kafka Message Bus (`rgba(251, 146, 60, 0.3)`
fill, `#fb923c` stroke) **in the gap** between the producing and consuming
services, ensuring it does not overlap service boxes. - Flows use correct SVG
marker arrowheads to indicate the direction of event publishing and consumption.

--------------------------------------------------------------------------------

## Cleanup

Revert or delete any `.html` files created during the test.
