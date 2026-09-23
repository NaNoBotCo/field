#!/usr/bin/env python3
"""bands.py — render a full-bleed parallax band. Pairs with bands.css.

Drop both into a project, include the CSS, and call band(). The host supplies its own
escaper and its own credit renderer, so this carries no opinion about where pictures
come from.

    from bands import band
    html = band("images/pai/canyon.jpg",
                kicker="Pai", head="Six hundred kilometres of this",
                line="Chiang Mai out, Pai, Mae Hong Son, home.",
                credit='Somebody · <a href="...">CC BY-SA 4.0</a>',
                href="legs/", cta="Every leg", cls="right tall")

WHAT MAKES IT WORK, AND WHAT BREAKS IT

  * Four layers. Photograph, scrim, tint, type. Two of them are pseudo-elements at
    negative z-index under an `isolation:isolate` parent, so they never escape the band.
  * Full bleed without knowing the column width: margin-inline:calc(50% - 50vw);width:100vw.
  * Pick the pictures BY HAND. An image search returns a lot that is true and useless.
    A band is the largest thing on the page and it cannot be filled by whatever sorted
    first.
  * Landscape only. `background-attachment:fixed` sizes the image to the VIEWPORT, not
    to the element, so a portrait photograph gets cropped to a letterbox of its middle.
  * A band is a heading. Do not print the same words as an <h2> underneath it.
"""
from __future__ import annotations

import html as _html


def _e(x) -> str:
    return _html.escape("" if x is None else str(x))


def band(image_url: str, kicker: str = "", head: str = "", line: str = "",
         big: str = "", big_label: str = "", href: str = "", cta: str = "",
         credit: str = "", cls: str = "", escape=_e) -> str:
    """One band. Returns "" with no image, so a band never ships as a black strip."""
    if not image_url:
        return ""
    inner = []
    if kicker:
        inner.append(f'<span class="kicker">{escape(kicker)}</span>')
    if big:
        label = f"<small>{escape(big_label)}</small>" if big_label else ""
        inner.append(f'<p class="big">{escape(big)}{label}</p>')
    if head:
        inner.append(f"<h2>{escape(head)}</h2>")
    if line:
        inner.append(f"<p>{escape(line)}</p>")
    if href and cta:
        inner.append(f'<a class="btn" href="{escape(href)}">{escape(cta)}</a>')
    cred = f'<span class="cred">{credit}</span>' if credit else ""
    return (f'<section class="band {escape(cls)}" '
            f'style="background-image:url({escape(image_url)})">'
            f'<div class="in">{"".join(inner)}</div>{cred}</section>')
