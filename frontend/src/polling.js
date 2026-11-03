// A stopped or replaced poll never schedules another request.
export function createPoller(task, { interval = 3000, maxDelay = 30000, onError = () => {} } = {}) {
  let timer, generation = 0;
  const stop = () => { generation++; clearTimeout(timer); };
  const start = () => {
    stop();
    const token = generation;
    let failures = 0;
    const tick = async () => {
      if (token !== generation) return;
      try {
        await task();
        failures = 0;
      } catch (error) {
        if (token !== generation) return;
        failures++;
        onError(error);
        if (error.status === 401) { stop(); return; }
      }
      if (token === generation) timer = setTimeout(tick, Math.min(interval * 2 ** Math.min(failures, 5), maxDelay));
    };
    timer = setTimeout(tick, interval);
  };
  return { start, stop };
}
