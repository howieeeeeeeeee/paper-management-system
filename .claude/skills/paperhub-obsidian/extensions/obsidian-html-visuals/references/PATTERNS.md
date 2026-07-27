# HTML Patterns

Adapt one pattern rather than combining several decorative styles.

## Process boxes

```html
<div style="overflow-x:auto; margin:12px 0;">
  <table style="width:100%; min-width:540px; table-layout:fixed; border-collapse:separate; border-spacing:6px;">
    <tr>
      <td style="padding:10px; vertical-align:top; border:1px solid var(--background-modifier-border); border-radius:6px; background:var(--background-secondary); color:var(--text-normal);"><strong>1 · Observe</strong><br><span style="color:var(--text-muted);">See the first signal.</span></td>
      <td style="padding:10px; vertical-align:top; border:1px solid var(--background-modifier-border); border-radius:6px; background:var(--background-secondary); color:var(--text-normal);"><strong>2 · Decide</strong><br><span style="color:var(--text-muted);">Enter the first belief.</span></td>
      <td style="padding:10px; vertical-align:top; border:1px solid var(--background-modifier-border); border-radius:6px; background:var(--background-secondary); color:var(--text-normal);"><strong>3 · Update</strong><br><span style="color:var(--text-muted);">Report the final belief.</span></td>
    </tr>
  </table>
</div>
```

## Two-condition comparison

```html
<div style="overflow-x:auto; margin:12px 0;">
  <table style="width:100%; min-width:520px; table-layout:fixed; border-collapse:collapse; color:var(--text-normal);">
    <thead>
      <tr>
        <th style="padding:8px; text-align:left; border:1px solid var(--background-modifier-border); background:var(--background-secondary);">Feature</th>
        <th style="padding:8px; text-align:left; border:1px solid var(--background-modifier-border); background:var(--background-secondary);">Condition A</th>
        <th style="padding:8px; text-align:left; border:1px solid var(--background-modifier-border); background:var(--background-secondary);">Condition B</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding:8px; vertical-align:top; border:1px solid var(--background-modifier-border);"><strong>What appears</strong></td>
        <td style="padding:8px; vertical-align:top; border:1px solid var(--background-modifier-border);">Exact signals only</td>
        <td style="padding:8px; vertical-align:top; border:1px solid var(--background-modifier-border);">Exact and coarse signals</td>
      </tr>
    </tbody>
  </table>
</div>
```

## Subject-view schematic

```html
<div style="margin:12px 0; padding:12px; border:1px solid var(--background-modifier-border); border-radius:6px; background:var(--background-secondary); color:var(--text-normal);">
  <div style="font-weight:600;">Schematic · what the subject sees</div>
  <div style="margin:8px 0; display:grid; grid-template-columns:repeat(auto-fit,minmax(72px,1fr)); gap:6px;">
    <div style="padding:10px 4px; text-align:center; border:1px solid var(--background-modifier-border); border-radius:4px; background:var(--background-primary);"><strong>130</strong></div>
    <div style="padding:10px 4px; text-align:center; border:1px solid var(--background-modifier-border); border-radius:4px; background:var(--background-primary);"><strong>150</strong></div>
    <div style="padding:10px 4px; text-align:center; border:1px solid var(--background-modifier-border); border-radius:4px; background:var(--background-primary);"><strong>70</strong></div>
  </div>
  <div style="padding-top:8px; border-top:1px solid var(--background-modifier-border); color:var(--text-muted);">Enter your estimate:</div>
</div>
```

Place any hidden values or analyst reconstruction in a separate block below this panel.
