// 外壳级状态：配色方案（V2 的森绿 / 纯白 / 暖纸）
import { ref } from 'vue'
import { toast } from './useToast'

const palettes = [
  ['forest', '森绿'],
  ['white', '纯白'],
  ['paper', '暖纸'],
] as const
export const paletteIndex = ref(0)

export function cyclePalette() {
  paletteIndex.value = (paletteIndex.value + 1) % palettes.length
  const [id, name] = palettes[paletteIndex.value]
  document.body.dataset.palette = id
  toast(`配色方案 ${paletteIndex.value + 1} / 3 · ${name}`)
}
export const paletteName = () => palettes[paletteIndex.value][1]
