export function clampFloatingPanelPosition ({
  x,
  y,
  containerWidth,
  containerHeight,
  panelWidth,
  panelHeight,
  inset = 10
}) {
  const safeInset = Math.max(0, Number(inset) || 0)
  const maxX = Math.max(safeInset, Number(containerWidth) - Number(panelWidth) - safeInset)
  const maxY = Math.max(safeInset, Number(containerHeight) - Number(panelHeight) - safeInset)
  return {
    x: Math.max(safeInset, Math.min(maxX, Number(x) || 0)),
    y: Math.max(safeInset, Math.min(maxY, Number(y) || 0))
  }
}

export function snapFloatingPanelPosition (position, dimensions, threshold = 22) {
  const clamped = clampFloatingPanelPosition({ ...position, ...dimensions })
  const inset = Math.max(0, Number(dimensions.inset) || 0)
  const maxX = Math.max(inset, Number(dimensions.containerWidth) - Number(dimensions.panelWidth) - inset)
  const maxY = Math.max(inset, Number(dimensions.containerHeight) - Number(dimensions.panelHeight) - inset)
  const snap = Math.max(0, Number(threshold) || 0)
  return {
    x: clamped.x - inset <= snap ? inset : (maxX - clamped.x <= snap ? maxX : clamped.x),
    y: clamped.y - inset <= snap ? inset : (maxY - clamped.y <= snap ? maxY : clamped.y)
  }
}
