# Wardrobe UX Review

Generated from Claude review on 2026-05-12.

## Implemented/Recommended Patch Plan

### 1. Dress Tab — Active Slot Guidance

Problem: tapping a body hotspot or slot button gives weak visual feedback, and the picker grid appears below the fold with no scroll hint.

Recommended fixes:
- Add `data-slot` attributes to avatar hotspots and route them through the delegated slot handler.
- In `selectSlot()`, toggle an active class on the matching `.body-hotspot` and update `aria-pressed`.
- Add a stronger `.body-hotspot.active` style.
- Scroll or guide the user toward the picker after selecting a slot.

### 2. Dress Tab — Original / Game Thumbnail Toggle

Problem: the Dress tab picker hardcoded thumbnail URLs and did not fully participate in the global Originals/Game thumbnails image-mode switch.

Recommended fixes:
- Add the same image-mode switch affordance near the Dress picker.
- Use `imageFor(item)` for Dress picker and selected-look thumbnails.
- Add `.wardrobe-img`, `data-original`, and `data-thumbnail` attributes so `setImageMode()` updates Dress images too.

### 3. Selected Item Summary

Problem: no at-a-glance count of filled slots, and selected rows give minimal guidance.

Recommended fixes:
- Show a slot count such as “2 of 5 slots filled”.
- Disable or visually de-emphasize the Gemini generation button until at least one item is selected.
- Show selected item category/subcategory clearly.

### 4. Dress Tab Layout Clarity

Problem: slot controls and picker title feel visually disconnected.

Recommended fixes:
- Keep the current active slot title/instructions close to the selector.
- Add sticky/mobile guidance above the picker so it is obvious that clothes appear below.

## Additional Issues / Improvements

1. Replace disruptive `alert()` calls with inline status messages.
2. Replace fragile inline `onclick` serialization in outfit cards with delegated handlers.
3. Add `cursor: pointer` to slot and hotspot controls.
4. Standardize copy: “Outerwear” instead of “Outer”.
5. Improve detail modal fallback copy: “Original photo (no game thumbnail)” instead of “Original fallback”.
6. Add loading state/spinner for Gemini generation.
7. Add a loading placeholder for the Dress picker before items load.
8. Add small transitions to picker re-renders.
9. Consider sticky bottom action bar on mobile for “Dress avatar with Gemini”.
10. Consider grouping items by category/slot with clearer labels and counts.
