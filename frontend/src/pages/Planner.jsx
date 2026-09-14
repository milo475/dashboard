import { useCallback, useEffect, useState } from 'react'
import { postJson, usePolling } from '../api.js'
import { TodayCard } from '../components/planner/TodayCard.jsx'
import { TodoCard } from '../components/planner/TodoCard.jsx'
import { PlacesCard } from '../components/planner/PlacesCard.jsx'
import { ScheduleCard } from '../components/planner/ScheduleCard.jsx'
import { PhotosCard } from '../components/planner/PhotosCard.jsx'

/* The planner page, laid out like the desktop it is modelled on: calendar,
 * routine and the day's agenda top-left, the to-do note in the middle, folder
 * and file shortcuts top-right, the week across the bottom with a photo
 * collage beside it.
 *
 * The schedule and the photo list are owned here because two cards read each:
 * the Today tile shows today's blocks and the first photo, so an edit in the
 * schedule card must reach it without waiting for the next poll. */
export function Planner() {
  const schedule = usePolling('/api/schedule', 60_000)
  // A short poll so a file copied into the folder shows up within seconds.
  const photos = usePolling('/api/photos', 20_000)
  const [localSchedule, setLocalSchedule] = useState(null)
  const [scheduleError, setScheduleError] = useState(null)

  const scheduleState = localSchedule ?? (schedule.data?.available ? schedule.data : null)

  useEffect(() => {
    // Adopt the server's copy whenever a fresh poll lands; local wins only
    // until its own write comes back.
    if (schedule.data?.available) setLocalSchedule(null)
  }, [schedule.data])

  const saveSchedule = useCallback(
    async (days) => {
      setLocalSchedule({ ...(scheduleState ?? {}), days })
      setScheduleError(null)
      try {
        const body = await postJson('/api/schedule', { days })
        if (body?.available) setLocalSchedule(body)
        else {
          setScheduleError(body?.error ?? 'could not save')
          schedule.reload()
        }
      } catch (err) {
        setScheduleError(err.message || 'could not save')
        schedule.reload()
      }
    },
    [schedule, scheduleState],
  )

  const photoList = photos.data?.available ? photos.data.photos : []
  const todayKey = scheduleState?.today
  const todayBlocks = todayKey ? scheduleState.days[todayKey] ?? [] : []

  return (
    <main className="grid grid-planner">
      <TodayCard blocks={todayBlocks} photo={photoList[0] ?? null} />
      <TodoCard />
      <PlacesCard />
      <ScheduleCard
        state={scheduleState}
        loading={schedule.loading && !schedule.data}
        error={schedule.data ? null : schedule.error}
        unavailable={schedule.data && !schedule.data.available ? schedule.data : null}
        saveError={scheduleError}
        onChange={saveSchedule}
      />
      <PhotosCard
        photos={photoList}
        dir={photos.data?.dir}
        loading={photos.loading && !photos.data}
        error={photos.data ? null : photos.error}
        reload={photos.reload}
      />
    </main>
  )
}
