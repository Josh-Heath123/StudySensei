// Chromium APIs the spike uses that TypeScript's DOM library doesn't declare yet.

/** Breakout Box: https://w3c.github.io/mediacapture-transform/ (Chromium). */
declare class MediaStreamTrackProcessor<T = VideoFrame> {
  constructor(init: { track: MediaStreamTrack; maxBufferSize?: number });
  readonly readable: ReadableStream<T>;
}

/** Document Picture-in-Picture: https://wicg.github.io/document-picture-in-picture/ (Chromium). */
interface DocumentPictureInPicture extends EventTarget {
  requestWindow(options?: { width?: number; height?: number }): Promise<Window>;
  readonly window: Window | null;
}
declare const documentPictureInPicture: DocumentPictureInPicture | undefined;

/** User-Agent Client Hints: https://wicg.github.io/ua-client-hints/ (Chromium). */
interface NavigatorUAData {
  readonly brands: { brand: string; version: string }[];
  readonly platform: string;
  getHighEntropyValues(
    hints: string[],
  ): Promise<{ fullVersionList?: { brand: string; version: string }[]; platformVersion?: string }>;
}
interface Navigator {
  readonly userAgentData?: NavigatorUAData;
}
