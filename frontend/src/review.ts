export type ReviewBook = { id: string; title: string; version: string; point_count: number; page_count: number; coverage_label: string }
export type TocNode = { id: string; title: string; parent_id: string | null; point_id: string | null; level: number; path: string[]; page: number }
export type ContentBlock = { id: string; type: 'paragraph' | 'figure'; text?: string; asset_id?: string; width?: number; height?: number; alt?: string; page: number; bbox: number[] }
export type KnowledgePoint = { id: string; book_id: string; version: string; title: string; path: string[]; blocks: ContentBlock[]; source_start: number; source_end: number; previous_id: string | null; next_id: string | null }
