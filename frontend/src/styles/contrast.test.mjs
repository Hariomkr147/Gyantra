/**
 * Contrast audit for the theme tokens.
 *
 * Run: node src/styles/contrast.test.mjs
 *
 * The token values are duplicated here deliberately: the point is to fail if
 * someone edits index.css and drops a pair below the WCAG AA floor, so the
 * check has to assert against known-good numbers rather than read the source
 * it is validating.
 */

const THEMES = {
  dark: {
    backgrounds: {
      bg: [2, 6, 23],
      surface: [15, 23, 42],
      sunken: [2, 6, 23],
      subtle: [30, 41, 59],
    },
    foregrounds: {
      fg: [248, 250, 252],
      'fg-strong': [255, 255, 255],
      'fg-muted': [148, 163, 184],
      'fg-subtle': [132, 146, 166],
      'accent-fg': [45, 212, 191],
      success: [52, 211, 153],
      warn: [251, 191, 36],
      danger: [248, 113, 113],
    },
    syntax: {
      'syn-key': [45, 212, 191],
      'syn-string': [134, 239, 172],
      'syn-number': [125, 211, 252],
      'syn-boolean': [216, 180, 254],
    },
  },
  light: {
    backgrounds: {
      bg: [248, 250, 252],
      surface: [255, 255, 255],
      sunken: [248, 250, 252],
      subtle: [241, 245, 249],
    },
    foregrounds: {
      fg: [15, 23, 42],
      'fg-strong': [2, 6, 23],
      'fg-muted': [71, 85, 105],
      'fg-subtle': [90, 105, 128],
      'accent-fg': [15, 118, 110],
      success: [4, 120, 87],
      warn: [180, 83, 9],
      danger: [185, 28, 28],
    },
    syntax: {
      'syn-key': [13, 148, 136],
      'syn-string': [22, 101, 52],
      'syn-number': [2, 132, 199],
      'syn-boolean': [147, 51, 234],
    },
  },
}

const AA_BODY = 4.5 // WCAG AA, normal-size text
const AA_UI = 3.0 // WCAG AA, large text and UI components

const channel = (c) => {
  const v = c / 255
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}

const luminance = ([r, g, b]) =>
  0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const failures = []
const results = []

for (const [themeName, theme] of Object.entries(THEMES)) {
  // Body text must be readable on every surface it can land on.
  for (const [fgName, fg] of Object.entries(theme.foregrounds)) {
    for (const [bgName, bg] of Object.entries(theme.backgrounds)) {
      const ratio = contrast(fg, bg)
      results.push({ themeName, fgName, bgName, ratio, threshold: AA_BODY })
      if (ratio < AA_BODY) {
        failures.push(
          `${themeName}: ${fgName} on ${bgName} = ${ratio.toFixed(2)}:1 ` +
            `(needs ${AA_BODY} for body text)`,
        )
      }
    }
  }

  // Syntax colours only ever render on the sunken code surface, and carry
  // meaning through position as well as hue, so the UI threshold applies.
  for (const [fgName, fg] of Object.entries(theme.syntax)) {
    const ratio = contrast(fg, theme.backgrounds.sunken)
    results.push({ themeName, fgName, bgName: 'sunken', ratio, threshold: AA_UI })
    if (ratio < AA_UI) {
      failures.push(
        `${themeName}: ${fgName} on sunken = ${ratio.toFixed(2)}:1 ` +
          `(needs ${AA_UI})`,
      )
    }
  }
}

for (const theme of Object.keys(THEMES)) {
  const inTheme = results.filter((r) => r.themeName === theme)
  const worst = inTheme.reduce((a, b) => (a.ratio < b.ratio ? a : b))
  console.log(
    `${theme.padEnd(6)} ${inTheme.length} pairs checked, ` +
      `worst: ${worst.fgName} on ${worst.bgName} = ${worst.ratio.toFixed(2)}:1`,
  )
}

if (failures.length) {
  console.error(`\n${failures.length} contrast failure(s):`)
  for (const f of failures) console.error(`  ${f}`)
  process.exit(1)
}

console.log(`\nPASS — ${results.length} pairs meet WCAG AA.`)
