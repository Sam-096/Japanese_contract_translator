interface ImagePreviewProps {
  url: string
}

export function ImagePreview({ url }: ImagePreviewProps) {
  return (
    <img
      src={url}
      alt="Original document"
      className="w-full rounded-lg border border-border shadow-sm"
    />
  )
}
