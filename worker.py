import os, time, logging, schedule

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

TZ = os.getenv("TZ", "Europe/Athens")
EOD_TIME = os.getenv("EOD_TIME", "23:59")

def send_daily_report():
    try:
        log.info("Generating & sending daily report...")
        # TODO: integrate reports.day_report + telegram.api
    except Exception:
        log.exception("Daily report failed")

if __name__ == "__main__":
    log.info(f"Starting worker (TZ={TZ})")
    schedule.every().day.at(EOD_TIME).do(send_daily_report)
    while True:
        schedule.run_pending()
        time.sleep(1)
