# Admin measurements, 2026-09-14

Read from Hudson's signed-in admin (store wedydn-u1) in his own Chrome at a
1194 wide viewport, plus the Home page re-rendered at 1440 by 900. These are
the numbers the Polaris build copies. The skill in the vault carries the full
token diff; this file keeps the per-page facts.

## Frame

- Top bar 56 tall, rgb(10,10,10). Search pill 640 by 36 at radius 12, fill
  rgb(40,40,40), label 13px 400 rgb(220,220,220), 20px search glyph, two 20px
  keys in rgb(47,47,47) with rgb(170,170,170) 12/16 550 text. Icon buttons 36
  by 36 radius 12. Store chip: 28px avatar, 4 gap, name 12/16 550.
- Nav 240 wide on rgb(235,235,235), top-left radius 12, list padding 12 0,
  rows 218 by 28 at x 10, padding 0 4 0 8, 20px icon slot with a 16px glyph at
  rgb(48,48,48), text 13/20 550, selected 600 on rgb(250,250,250). Section
  heading is a 24px button with a 5px caret; sub-items indent 36 and use
  rgb(97,97,97).
- Main under the bar with radius 12 12 0 0 on rgb(241,241,241). Home's own
  surface is rgb(251,251,251).

## Page header

- Title 18/24 600 with letter-spacing -0.15px, 4px after the back button.
- Header buttons are 28 tall at radius 8. The primary Save is 12/16 600 white
  on rgb(48,48,48); disabled it sits on rgba(0,0,0,.17).

## Products index

- IndexFilters: tab pill 28 tall, padding 4 12, 12/16 550, active fill
  rgba(0,0,0,.08); disabled "add view" pill rgba(0,0,0,.05). Search and sort
  are 28px icon buttons.
- Empty state: two 380 wide columns with a 40 gap inside a 1024 max, heading,
  paragraph, then the actions with 16 top padding.

## Product form

- Two columns: primary 578 wide (546 inside 16 padding), secondary 280, gap 16.
- Card heading 13/20 600, sections 16 padding with 8 between fields.
- Text field label 13/20 450 with 4 below, control 32 tall.

## Analytics

- Metric card header margin 16 16 0, heading 13/16 600, gap 8 to the metric
  definition glyph.
