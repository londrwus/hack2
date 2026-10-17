# SiteMind light UI spec (fallback: the Pen app could not open a file)

Tokens: canvas #F3F3F2, card #FFF, hairline #E7E7E5, ink #1F1F1F / ink-2 #2A2A2A, subtle #EFEFED, muted text #74746F, badge-blue #1E5AA8.
Status: ok #1F9D55, warn #E8A10A, risk #E5484D. Data: amber #E8B10A, orange #F26B1D, sky #19B6E8, teal #18B5A5, pink #EC4899.
Radius: cards 18px, buttons 10px, chips 8px. Shadow: `--shadow-soft`. Font: Inter, tabular numbers, sentence case.

Shell: a 248px sidebar on the canvas. It has a workspace row, search with a "/" hint, the Essentials group (Overview, Clips, 3D twin) and the Work group (Analyse, Model). At the bottom are Help & support and a "Site supervisor" profile card. The active nav item is a white card with a hairline border.

Pages:
- Overview: a row of 4 StatCards, a SectionCard listing workers who need a check-in (StatusPill per worker), and a clip grid of 16:9 thumbnails with a pill and a time.
- Clip detail: the video on the left at 8 columns, with a signals timeline below it. On the right: a "Fit for height work" verdict card, worker cards, and a signpost card (Lighthouse Club 0345 605 1956 / Samaritans 116 123).
- 3D twin: an off-white viewport with drop edges in red. On the right, an inspector with segmented layer toggles. A mini-map sits bottom-left.
- Analyse: a CloudHero with a white circle upload icon, a dark "Upload clip" button, and a RingProgress showing "2 of 4".
- Model: SectionCards with a StackedBar and a Legend table, plus a footer chip.
- Operator: a right-side OperatorPanel with a UserBubble, a ThoughtLink and embedded SectionCards.
