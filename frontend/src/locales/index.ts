import en from './en'
import zh from './zh'
import pt from './pt'

export default {
  en,
  zh,
  pt
}

export type Locale = 'en' | 'zh' | 'pt'

export const availableLocales: { label: string; value: Locale }[] = [
  { label: 'Português (Brasil)', value: 'pt' },
  { label: 'English', value: 'en' },
  { label: '中文', value: 'zh' }
]