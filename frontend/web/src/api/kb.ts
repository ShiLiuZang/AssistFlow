// 知识库接口。类型对照后端 app/api/kb.py 的 overview() 返回值手写。
// 以后可以用 openapi-typescript 从 FastAPI 的 /openapi.json 自动生成，不用再手写。
import { getJson } from './client'

export interface KbChunkStats {
  total: number | null
  done: number | null
  pending: number | null
  key_clause: number | null
  by_content_type: Record<string, number>
}

export interface KbMilvusState {
  online: boolean
  count: number | null
  collection?: string
}

export interface KbOverview {
  chunks: KbChunkStats
  milvus: KbMilvusState
  consistent: boolean | null // null 表示无法判断（数据库或向量库不可用）
  db_error: string | null
}

export const getKbOverview = () => getJson<KbOverview>('/api/kb/overview')
