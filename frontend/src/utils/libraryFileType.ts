/**
 * Library file-type classification (TAREFA 6.1).
 *
 * Pulled out of LibraryPage.vue so the classification rules are unit
 * testable without mounting the page. Matches the Manus Library filter
 * set: Slides / Sites / Documentos / Planilhas / Imagens / Áudio e Vídeo /
 * Outros — each file lands in exactly one bucket, extension checked first
 * since content_type is frequently a generic octet-stream for agent-written
 * files.
 */

export type LibraryDocType =
  | 'slides'
  | 'sites'
  | 'documents'
  | 'spreadsheets'
  | 'images'
  | 'audio_video'
  | 'others'

export interface ClassifiableFile {
  filename?: string | null
  file_path?: string | null
  content_type?: string | null
}

const SLIDE_EXTENSIONS = ['ppt', 'pptx', 'key', 'odp']
const SITE_EXTENSIONS = ['html', 'htm']
const DOCUMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'txt', 'md', 'rtf', 'pages', 'odt']
const SPREADSHEET_EXTENSIONS = ['xls', 'xlsx', 'csv', 'ods', 'numbers', 'tsv']
const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'tiff', 'ico']
const AUDIO_VIDEO_EXTENSIONS = [
  'mp4', 'mov', 'webm', 'avi', 'mkv', 'm4v',
  'mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac',
]

function extensionOf(f: ClassifiableFile): string {
  const name = f.filename || f.file_path || ''
  const i = name.lastIndexOf('.')
  return i > 0 ? name.slice(i + 1).toLowerCase() : ''
}

export function classifyLibraryFile(f: ClassifiableFile): LibraryDocType {
  const ext = extensionOf(f)
  const ct = f.content_type || ''

  if (SLIDE_EXTENSIONS.includes(ext)) return 'slides'
  if (SITE_EXTENSIONS.includes(ext) || ct === 'text/html') return 'sites'
  if (DOCUMENT_EXTENSIONS.includes(ext)) return 'documents'
  if (SPREADSHEET_EXTENSIONS.includes(ext)) return 'spreadsheets'
  if (IMAGE_EXTENSIONS.includes(ext) || ct.startsWith('image/')) return 'images'
  if (AUDIO_VIDEO_EXTENSIONS.includes(ext) || ct.startsWith('video/') || ct.startsWith('audio/')) {
    return 'audio_video'
  }
  return 'others'
}
