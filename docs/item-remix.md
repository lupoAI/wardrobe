# Item Remix

Adds a "Build outfit with this" action to item details.

## Behavior

- Open any wardrobe item from the Pieces tab.
- Tap **Build outfit with this**.
- The app switches to the planner and requests `/api/outfits/suggest` with `item_id`.
- Suggestions are generated with the selected item constrained into every candidate outfit, then scored by the existing outfit scoring logic.

## Implementation notes

- Core categories (`tops`, `bottoms`, `shoes`, `outerwear`) constrain the relevant candidate pool to the target item.
- Non-core items such as accessories are appended to candidates so the remix still works.
- Existing outfit save/rate behavior is reused unchanged.
