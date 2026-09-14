# Shop Ledger on Polaris, end to end

Decided 2026-09-14. Every screen is a copy of its counterpart page in the
live Shopify admin (store wedydn-u1), measured from Hudson's own Chrome and
checked against @shopify/polaris 13.9.5. This is the map of what each screen
copies and which components exist because of it.

## Screens and their counterparts

- Today (`index.html`) copies Analytics: metric cards in a grid, each with a
  heading, a large number, a delta badge and a sparkline, then the two ranked
  lists as cards with resource rows, and the health strip as a subdued card.
- Products (`products.html`) copies the Products index: page header with a
  primary action, an IndexFilters bar (tabs, search, sort), an IndexTable with
  thumbnail rows, status badges, sortable headings, sticky header and a
  pagination footer, and the FooterHelp line.
- Product detail (`products/<id>.html`) copies a product page: back button,
  title, previous and next pagination, a two-column layout (primary 2/3 and a
  fixed 280 secondary), cards with headings and sections, a description list,
  a variants table and a resource list of videos.
- Videos (`videos.html`) copies the Orders index: the same IndexFilters and
  IndexTable with tall thumbnails, type badges and money columns.
- Creators (`creators.html`) copies the Customers index: avatars with initials
  in the Polaris avatar palette, name and subtext, numeric columns.
- Data health (`health.html`) copies Settings and Reports pages: an info
  Banner for partial intervals, metric cards, then two IndexTables.

## Components, all Polaris verbatim

- Frame: dark top bar (56, rgb(10,10,10)) with the search pill, keyboard keys,
  status chips and the store chip; 240 nav with 16px glyphs, section
  headings with carets, selected row fill; main with 12px top corners; below
  48em a hamburger and a sliding nav drawer (300ms ease-out) with backdrop.
- Page header: back button, title 18/24 600, optional badge, secondary and
  primary buttons, previous and next arrows on detail pages.
- Buttons: primary (gradient plus three-inset bevel), secondary (white plus
  bevel), tertiary, plain, icon-only, disabled, loading with the spinner.
- Badges: default, success, critical, warning, info, attention, new, plus the
  progress dot variants (incomplete, partial, complete) used for confidence.
- Card: bevelled, radius 12, padding 16, header row with heading-sm and
  actions, dividers between sections, subdued section, footer.
- IndexFilters: tab pills (active rgba(0,0,0,.08)), search field, sort button
  that opens a Popover with an ActionList of radio choices.
- IndexTable: heading row on bg-surface-secondary, 12/16 550 headings with
  sort caret, cells 8px 16px, rows divided on top, hover fill, sticky header,
  client-side sorting and paging (50 a page) with a Pagination footer.
- TextField, Select and Checkbox with the 0.66px hairline, focus ring and
  hover states. Search fields carry the search glyph and a clear button.
- Banner (info, warning, critical, success) in page and in card forms.
- EmptyState with heading, body and one action.
- Skeleton body text and display text, static grey, for cells with no reading.
- Spinner (small in buttons and fields).
- Toast, rising from the bottom centre (400ms in, 200ms out), used when an ID
  is copied.
- Tooltip on truncated titles and on confidence badges (appear-above, 50ms).
- Popover with ActionList for the sort menu and the window picker.
- ProgressBar (small, primary) for share of views.
- Avatar (7 tone palette, initials) and Thumbnail (40 and 40 by 56).
- DescriptionList for facts. KeyboardKey in the search pill.
- Frame loading bar (3px, brand fill, 500ms linear) on every navigation.
- FooterHelp under index pages.

## Laws applied

- Light only. The experimental dark block is gone because the admin has none.
- Nothing animates that Polaris does not animate, at Polaris durations.
- Weights 450 / 550 / 600 / 650 as the live admin renders them.
- Colour enters through status tokens, the link blue and the chart series.
  The chart series is a Shop Ledger token, named `--sl-*`, never `--p-*`.
- Shopify's name, logo and wordmark never appear.

## Verification

- `docs/polaris-home-replica/` remains the pixel reference for the frame.
- Each screen is screenshotted at 1440 by 900 and at 390 wide after render
  and compared with the admin measurements in `docs/admin-measurements.md`.
