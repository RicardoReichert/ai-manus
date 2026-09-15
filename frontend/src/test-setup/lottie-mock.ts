import { vi } from 'vitest'

// jsdom doesn't implement HTMLCanvasElement.getContext(), so lottie-web's
// real renderer crashes (`Cannot set properties of null (setting
// 'fillStyle')`) the moment any component mounts LiveStatusCanvas.vue.
// Stub the whole module with a no-op animation so component/route tests
// that merely render the canvas don't need a real canvas backend.
vi.mock('lottie-web', () => ({
  default: {
    loadAnimation: () => ({
      destroy: () => {},
      setSpeed: () => {},
      play: () => {},
      stop: () => {},
    }),
  },
}))
