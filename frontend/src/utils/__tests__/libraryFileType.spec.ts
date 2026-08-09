import { describe, it, expect } from 'vitest'
import { classifyLibraryFile, type LibraryDocType } from '../libraryFileType'

const file = (overrides: { filename?: string; content_type?: string }): {
  filename?: string
  content_type?: string
} => overrides

describe('classifyLibraryFile', () => {
  const cases: Array<[string, { filename?: string; content_type?: string }, LibraryDocType]> = [
    ['pptx by extension', file({ filename: 'deck.pptx' }), 'slides'],
    ['ppt by extension', file({ filename: 'deck.ppt' }), 'slides'],
    ['key by extension', file({ filename: 'deck.key' }), 'slides'],
    ['html by extension', file({ filename: 'index.html' }), 'sites'],
    ['html by content_type', file({ filename: 'page', content_type: 'text/html' }), 'sites'],
    ['pdf by extension', file({ filename: 'report.pdf' }), 'documents'],
    ['docx by extension', file({ filename: 'report.docx' }), 'documents'],
    ['md by extension', file({ filename: 'notes.md' }), 'documents'],
    ['xlsx by extension', file({ filename: 'data.xlsx' }), 'spreadsheets'],
    ['csv by extension', file({ filename: 'data.csv' }), 'spreadsheets'],
    ['png by extension', file({ filename: 'shot.png' }), 'images'],
    ['image content_type', file({ filename: 'shot', content_type: 'image/jpeg' }), 'images'],
    ['mp4 by extension', file({ filename: 'clip.mp4' }), 'audio_video'],
    ['mp3 by extension', file({ filename: 'track.mp3' }), 'audio_video'],
    ['video content_type', file({ filename: 'clip', content_type: 'video/webm' }), 'audio_video'],
    ['audio content_type', file({ filename: 'track', content_type: 'audio/mpeg' }), 'audio_video'],
    ['zip falls to others', file({ filename: 'archive.zip' }), 'others'],
    ['no extension falls to others', file({ filename: 'README' }), 'others'],
    ['no filename at all falls to others', file({}), 'others'],
  ]

  it.each(cases)('%s', (_label, f, expected) => {
    expect(classifyLibraryFile(f)).toBe(expected)
  })

  it('extension takes priority when content_type is generic/absent', () => {
    expect(classifyLibraryFile({ filename: 'report.pdf', content_type: 'application/octet-stream' }))
      .toBe('documents')
  })
})
