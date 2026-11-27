/** What POST /api/token returns: everything the browser needs to join one LiveKit room. */
export type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantToken: string;
};

export type TokenError = {
  error: string;
};
