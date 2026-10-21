// O PTS codificado pode arredondar o início do frame; buscar seu interior evita o anterior.
export function frameSeekTime(index: number, fps: number): number {
  return (index + 0.5) / fps;
}
