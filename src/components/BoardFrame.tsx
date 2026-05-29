interface BoardFrameProps {
  baseUrl: string;
  accessToken: string;
}

export function BoardFrame({ baseUrl, accessToken }: BoardFrameProps) {
  const src = `${baseUrl.replace(/\/$/, "")}/board/${encodeURIComponent(accessToken)}?embed=1`;

  return (
    <iframe
      className="board-frame"
      title="Tavle whiteboard"
      src={src}
      allow="clipboard-read; clipboard-write"
    />
  );
}
