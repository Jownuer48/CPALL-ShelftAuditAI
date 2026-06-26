import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const MODELS = ['MODEL_A', 'MODEL_B', 'MODEL_C']
const MODEL_DESCRIPTIONS = {
  MODEL_A: 'Shelf model A planogram',
  MODEL_B: 'Shelf reference model B',
  MODEL_C: 'Shelf reference model C',
}
const DEFAULT_CANVAS_SIZE = { width: 800, height: 500 }
const MAX_CANVAS_WIDTH = 1050
const MIN_BOX_SIZE = 10

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000
}

function clamp01(value) {
  const number = Number(value)

  if (!Number.isFinite(number)) {
    return 0
  }

  return Math.min(1, Math.max(0, number))
}

function defaultThreshold(type) {
  return type === 'promo' ? 0.45 : 0.55
}

function modelPrefix(modelId) {
  if (modelId === 'MODEL_A') return 'A'
  if (modelId === 'MODEL_B') return 'B'
  if (modelId === 'MODEL_C') return 'C'
  return 'X'
}

function descriptionForModel(modelId) {
  return MODEL_DESCRIPTIONS[modelId] || 'Shelf planogram'
}

function emptyDraft() {
  return {
    slot_id: '',
    type: 'product',
    label: '',
    threshold: '0.55',
  }
}

function draftFromSlot(slot) {
  return {
    slot_id: slot.slot_id,
    type: slot.type,
    label: slot.label || '',
    threshold: String(slot.threshold ?? defaultThreshold(slot.type)),
  }
}

function normalizeSlot(slot, index, modelId) {
  const type = slot?.type === 'promo' ? 'promo' : 'product'
  const kind = type === 'promo' ? 'PROMO' : 'PRODUCT'
  const fallbackId = `${modelPrefix(modelId)}_${kind}_${String(index + 1).padStart(2, '0')}`
  const threshold = Number(slot?.threshold)

  return {
    slot_id: String(slot?.slot_id || fallbackId),
    type,
    label: String(slot?.label || ''),
    x: round4(clamp01(slot?.x)),
    y: round4(clamp01(slot?.y)),
    w: round4(clamp01(slot?.w)),
    h: round4(clamp01(slot?.h)),
    threshold: Number.isFinite(threshold) ? threshold : defaultThreshold(type),
  }
}

function App() {
  const canvasRef = useRef(null)
  const imageRef = useRef(null)
  const jsonTextRef = useRef(null)
  const drawingRef = useRef({
    isDrawing: false,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
  })

  const [modelId, setModelId] = useState('MODEL_A')
  const [defaultType, setDefaultType] = useState('product')
  const [slots, setSlots] = useState([])
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const [draft, setDraft] = useState(emptyDraft)
  const [canvasSize, setCanvasSize] = useState(DEFAULT_CANVAS_SIZE)
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageInfo, setImageInfo] = useState('No reference image loaded')
  const [status, setStatus] = useState('Ready')

  const planogram = useMemo(
    () => ({
      model_id: modelId,
      description: descriptionForModel(modelId),
      slots: slots.map((slot) => ({
        slot_id: slot.slot_id,
        type: slot.type,
        label: slot.label,
        x: round4(slot.x),
        y: round4(slot.y),
        w: round4(slot.w),
        h: round4(slot.h),
        threshold: Number(slot.threshold ?? defaultThreshold(slot.type)),
      })),
    }),
    [modelId, slots],
  )

  const jsonText = useMemo(() => JSON.stringify(planogram, null, 2), [planogram])

  const selectedSlot = selectedIndex >= 0 ? slots[selectedIndex] : null

  const nextSlotId = useCallback(
    (type) => {
      const kind = type === 'promo' ? 'PROMO' : 'PRODUCT'
      const count = slots.filter((slot) => slot.type === type).length + 1
      return `${modelPrefix(modelId)}_${kind}_${String(count).padStart(2, '0')}`
    },
    [modelId, slots],
  )

  const getCanvasPoint = useCallback((event) => {
    const canvas = canvasRef.current

    if (!canvas) {
      return { x: 0, y: 0 }
    }

    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height

    return {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY,
    }
  }, [])

  const drawCanvas = useCallback(
    (previewRect = null) => {
      const canvas = canvasRef.current

      if (!canvas) {
        return
      }

      const ctx = canvas.getContext('2d')
      const width = canvas.width || DEFAULT_CANVAS_SIZE.width
      const height = canvas.height || DEFAULT_CANVAS_SIZE.height

      ctx.clearRect(0, 0, width, height)

      if (imageLoaded && imageRef.current) {
        ctx.drawImage(imageRef.current, 0, 0, width, height)
      } else {
        ctx.fillStyle = '#0b0f17'
        ctx.fillRect(0, 0, width, height)
      }

      slots.forEach((slot, index) => {
        const x = slot.x * width
        const y = slot.y * height
        const w = slot.w * width
        const h = slot.h * height
        const color = slot.type === 'promo' ? '#f97316' : '#22c55e'
        const selectedColor = '#38bdf8'
        const strokeColor = index === selectedIndex ? selectedColor : color
        const label = `${slot.slot_id} ${slot.label || ''}`.trim()
        const labelHeight = 24
        const labelY = y - labelHeight > 0 ? y - labelHeight : y

        ctx.save()
        ctx.strokeStyle = strokeColor
        ctx.lineWidth = index === selectedIndex ? 5 : 3
        ctx.strokeRect(x, y, w, h)

        ctx.font = '16px Arial, sans-serif'
        ctx.fillStyle = strokeColor
        ctx.fillRect(x, labelY, ctx.measureText(label).width + 14, labelHeight)

        ctx.fillStyle = '#ffffff'
        ctx.fillText(label, x + 7, labelY + 17)
        ctx.restore()
      })

      if (previewRect) {
        ctx.save()
        ctx.strokeStyle = '#38bdf8'
        ctx.lineWidth = 3
        ctx.setLineDash([8, 6])
        ctx.strokeRect(previewRect.x, previewRect.y, previewRect.w, previewRect.h)
        ctx.restore()
      }
    },
    [imageLoaded, selectedIndex, slots],
  )

  useEffect(() => {
    drawCanvas()
  }, [canvasSize, drawCanvas])

  function updateDraft(field, value) {
    setDraft((current) => ({ ...current, [field]: value }))
  }

  function selectSlot(index) {
    const slot = slots[index]

    if (!slot) {
      return
    }

    setSelectedIndex(index)
    setDraft(draftFromSlot(slot))
    setStatus(`${slot.slot_id} selected`)
  }

  function handleImageLoad(event) {
    const file = event.target.files?.[0]

    if (!file) {
      return
    }

    const reader = new FileReader()

    reader.onload = (loadEvent) => {
      const image = new Image()

      image.onload = () => {
        const scale = image.width > MAX_CANVAS_WIDTH ? MAX_CANVAS_WIDTH / image.width : 1
        const nextSize = {
          width: Math.round(image.width * scale),
          height: Math.round(image.height * scale),
        }

        imageRef.current = image
        setCanvasSize(nextSize)
        setImageLoaded(true)
        setImageInfo(
          `Image: ${file.name} | Original: ${image.width} x ${image.height} | Canvas: ${nextSize.width} x ${nextSize.height}`,
        )
        setStatus('Reference image loaded')
      }

      image.src = String(loadEvent.target?.result || '')
    }

    reader.readAsDataURL(file)
  }

  function handleModelChange(event) {
    const nextModelId = event.target.value

    setModelId(nextModelId)
    setSlots([])
    setSelectedIndex(-1)
    setDraft(emptyDraft())
    setStatus(`${nextModelId} selected; slots cleared`)
  }

  function handleMouseDown(event) {
    if (!imageLoaded) {
      setStatus('Load a reference image before drawing')
      return
    }

    const point = getCanvasPoint(event)
    drawingRef.current = {
      isDrawing: true,
      startX: point.x,
      startY: point.y,
      currentX: point.x,
      currentY: point.y,
    }
  }

  function handleMouseMove(event) {
    const drawing = drawingRef.current

    if (!drawing.isDrawing) {
      return
    }

    const point = getCanvasPoint(event)
    drawing.currentX = point.x
    drawing.currentY = point.y

    drawCanvas({
      x: Math.min(drawing.startX, drawing.currentX),
      y: Math.min(drawing.startY, drawing.currentY),
      w: Math.abs(drawing.currentX - drawing.startX),
      h: Math.abs(drawing.currentY - drawing.startY),
    })
  }

  function handleMouseUp() {
    const drawing = drawingRef.current

    if (!drawing.isDrawing) {
      return
    }

    drawing.isDrawing = false

    const x1 = Math.min(drawing.startX, drawing.currentX)
    const y1 = Math.min(drawing.startY, drawing.currentY)
    const x2 = Math.max(drawing.startX, drawing.currentX)
    const y2 = Math.max(drawing.startY, drawing.currentY)
    const w = x2 - x1
    const h = y2 - y1

    if (w < MIN_BOX_SIZE || h < MIN_BOX_SIZE) {
      drawCanvas()
      return
    }

    const type = defaultType
    const slot = {
      slot_id: nextSlotId(type),
      type,
      label: type === 'promo' ? 'Promo tag' : 'Product group',
      x: round4(x1 / canvasSize.width),
      y: round4(y1 / canvasSize.height),
      w: round4(w / canvasSize.width),
      h: round4(h / canvasSize.height),
      threshold: defaultThreshold(type),
    }

    setSlots((current) => [...current, slot])
    setSelectedIndex(slots.length)
    setDraft(draftFromSlot(slot))
    setStatus(`${slot.slot_id} added`)
  }

  function handleCanvasClick(event) {
    if (!imageLoaded || drawingRef.current.isDrawing) {
      return
    }

    const point = getCanvasPoint(event)

    for (let index = slots.length - 1; index >= 0; index -= 1) {
      const slot = slots[index]
      const x = slot.x * canvasSize.width
      const y = slot.y * canvasSize.height
      const w = slot.w * canvasSize.width
      const h = slot.h * canvasSize.height

      if (point.x >= x && point.x <= x + w && point.y >= y && point.y <= y + h) {
        selectSlot(index)
        return
      }
    }
  }

  function saveSelected() {
    if (!selectedSlot) {
      window.alert('Select a slot first')
      return
    }

    const type = draft.type === 'promo' ? 'promo' : 'product'
    const threshold = Number(draft.threshold)
    const updatedSlot = {
      ...selectedSlot,
      slot_id: draft.slot_id.trim() || selectedSlot.slot_id,
      type,
      label: draft.label.trim(),
      threshold: Number.isFinite(threshold) ? threshold : defaultThreshold(type),
    }

    setSlots((current) =>
      current.map((slot, index) => (index === selectedIndex ? updatedSlot : slot)),
    )
    setDraft(draftFromSlot(updatedSlot))
    setStatus('Selected slot saved')
  }

  function deleteSelected() {
    if (!selectedSlot) {
      window.alert('Select a slot first')
      return
    }

    if (!window.confirm('Delete selected slot?')) {
      return
    }

    setSlots((current) => current.filter((_, index) => index !== selectedIndex))
    setSelectedIndex(-1)
    setDraft(emptyDraft())
    setStatus('Selected slot deleted')
  }

  function clearSlots() {
    if (slots.length === 0) {
      setStatus('No slots to clear')
      return
    }

    if (!window.confirm('Clear all slots?')) {
      return
    }

    setSlots([])
    setSelectedIndex(-1)
    setDraft(emptyDraft())
    setStatus('All slots cleared')
  }

  async function copyJson() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(jsonText)
      } else if (jsonTextRef.current) {
        jsonTextRef.current.focus()
        jsonTextRef.current.select()
        document.execCommand('copy')
      }

      setStatus('JSON copied')
    } catch {
      window.alert('Copy failed. Select the JSON and press Ctrl+C.')
    }
  }

  function downloadJson() {
    const blob = new Blob([jsonText], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')

    link.href = url
    link.download = `${modelId.toLowerCase()}.json`
    link.click()
    URL.revokeObjectURL(url)
    setStatus('JSON downloaded')
  }

  function refreshJson() {
    drawCanvas()
    setStatus('JSON refreshed')
  }

  function handleJsonImport(event) {
    const file = event.target.files?.[0]

    if (!file) {
      return
    }

    const reader = new FileReader()

    reader.onload = (loadEvent) => {
      try {
        const data = JSON.parse(String(loadEvent.target?.result || '{}'))

        if (!Array.isArray(data.slots)) {
          throw new Error('Imported JSON must include a slots array.')
        }

        const importedModelId = MODELS.includes(data.model_id) ? data.model_id : modelId
        const importedSlots = data.slots.map((slot, index) => normalizeSlot(slot, index, importedModelId))

        setModelId(importedModelId)
        setSlots(importedSlots)
        setSelectedIndex(-1)
        setDraft(emptyDraft())
        setStatus(`Imported ${importedSlots.length} slots from ${file.name}`)
      } catch (error) {
        window.alert(error instanceof Error ? error.message : 'Could not import JSON.')
      } finally {
        event.target.value = ''
      }
    }

    reader.readAsText(file)
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <h1>CPALL Shelf Audit - Planogram Maker</h1>
          <p>{status}</p>
        </div>
        <div className="legend" aria-label="Box color legend">
          <span><i className="legend-swatch product" />product</span>
          <span><i className="legend-swatch promo" />promo</span>
          <span><i className="legend-swatch selected" />selected</span>
        </div>
      </header>

      <div className="layout">
        <section className="panel workspace-panel" aria-label="Planogram canvas editor">
          <div className="toolbar">
            <label className="control-group">
              <span>Reference Image</span>
              <input type="file" accept="image/*" onChange={handleImageLoad} />
            </label>

            <label className="control-group compact">
              <span>Model</span>
              <select value={modelId} onChange={handleModelChange}>
                {MODELS.map((model) => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
            </label>

            <label className="control-group compact">
              <span>Default Type</span>
              <select value={defaultType} onChange={(event) => setDefaultType(event.target.value)}>
                <option value="product">product</option>
                <option value="promo">promo</option>
              </select>
            </label>

            <button type="button" className="button muted" onClick={refreshJson}>Refresh JSON</button>
            <button type="button" className="button warning" onClick={clearSlots}>Clear All</button>
          </div>

          <div className="stats">{imageInfo}</div>

          <div className="canvas-wrap">
            <canvas
              ref={canvasRef}
              width={canvasSize.width}
              height={canvasSize.height}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onClick={handleCanvasClick}
              aria-label="Draw product or promo rectangles on the reference image"
            />
          </div>
        </section>

        <aside className="panel side-panel" aria-label="Planogram slot editor">
          <div className="side-section slots-section">
            <div className="section-title-row">
              <h2>Slots</h2>
              <span>{slots.length}</span>
            </div>

            <div className="slot-list">
              {slots.length === 0 ? (
                <div className="slot-empty">No slots yet</div>
              ) : (
                slots.map((slot, index) => (
                  <button
                    type="button"
                    key={`${slot.slot_id}-${index}`}
                    className={`slot-item${index === selectedIndex ? ' active' : ''}`}
                    onClick={() => selectSlot(index)}
                  >
                    <strong>{slot.slot_id}</strong>
                    <span>[{slot.type}]</span>
                    <small>{slot.label || '-'}</small>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="side-section editor-section">
            <h2>Edit Slot</h2>

            <label className="field">
              <span>slot_id</span>
              <input
                value={draft.slot_id}
                placeholder="A_PRODUCT_01"
                onChange={(event) => updateDraft('slot_id', event.target.value)}
              />
            </label>

            <label className="field">
              <span>type</span>
              <select value={draft.type} onChange={(event) => updateDraft('type', event.target.value)}>
                <option value="product">product</option>
                <option value="promo">promo</option>
              </select>
            </label>

            <label className="field">
              <span>label</span>
              <input
                value={draft.label}
                placeholder="Rexona group / Promo tag"
                onChange={(event) => updateDraft('label', event.target.value)}
              />
            </label>

            <label className="field">
              <span>threshold</span>
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={draft.threshold}
                onChange={(event) => updateDraft('threshold', event.target.value)}
              />
            </label>

            <div className="button-row">
              <button type="button" className="button" onClick={saveSelected}>Save Selected</button>
              <button type="button" className="button danger" onClick={deleteSelected}>Delete Selected</button>
            </div>
          </div>

          <div className="side-section json-section">
            <div className="section-title-row">
              <h2>Export JSON</h2>
              <label className="import-button">
                Import JSON
                <input type="file" accept=".json,application/json" onChange={handleJsonImport} />
              </label>
            </div>

            <div className="button-row">
              <button type="button" className="button" onClick={copyJson}>Copy JSON</button>
              <button type="button" className="button" onClick={downloadJson}>Download JSON</button>
            </div>

            <textarea ref={jsonTextRef} value={jsonText} readOnly aria-label="Planogram JSON output" />
          </div>
        </aside>
      </div>
    </main>
  )
}

export default App
