import { useSyncExternalStore } from 'react';

const q = '(max-width: 767px)';
const subscribe = (cb: () => void) => {
  const mq = matchMedia(q);
  mq.addEventListener('change', cb);
  return () => mq.removeEventListener('change', cb);
};
/** True below 768 px: drawer + bottom sheet layout. */
export const usePhone = (): boolean => useSyncExternalStore(subscribe, () => matchMedia(q).matches);
