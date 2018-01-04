import requests
import logging
import time
from pogom.utils import now
from datetime import datetime

'''' copied from pgo because it introduces dog-ugly dependencies through imports. No functional difference '''

log = logging.getLogger(__name__)


def handle_captcha_url(args, status, api, account, account_failures,
                       account_captchas, whq, captcha_url, step_location):
    try:
        if len(captcha_url) > 1:
            status['captcha'] += 1
            if not args.captcha_solving:
                status['message'] = ('Account {} has encountered a captcha. ' +
                                     'Putting account away.').format(
                                        account['username'])
                log.warning(status['message'])
                account_failures.append({
                    'account': account,
                    'last_fail_time': now(),
                    'reason': 'captcha found'})
                if args.webhooks:
                    wh_message = {'status_name': args.status_name,
                                  'status': 'encounter',
                                  'mode': 'disabled',
                                  'account': account['username'],
                                  'captcha': status['captcha'],
                                  'time': 0}
                    whq.put(('captcha', wh_message))
                return False

            if args.captcha_key and args.manual_captcha_timeout == 0:
                if automatic_captcha_solve(args, status, api, captcha_url,
                                           account, whq):
                    return True
                else:
                    account_failures.append({
                       'account': account,
                       'last_fail_time': now(),
                       'reason': 'captcha failed to verify'})
                    return False
            else:
                status['message'] = ('Account {} has encountered a captcha. ' +
                                     'Waiting for token.').format(
                                        account['username'])
                log.warning(status['message'])
                account['last_active'] = datetime.utcnow()
                account['last_location'] = step_location
                account_captchas.append((status, account, captcha_url))
                if args.webhooks:
                    wh_message = {'status_name': args.status_name,
                                  'status': 'encounter',
                                  'mode': 'manual',
                                  'account': account['username'],
                                  'captcha': status['captcha'],
                                  'time': args.manual_captcha_timeout}
                    whq.put(('captcha', wh_message))
                return False
    except KeyError as e:
        log.error('Unable to check captcha: {}'.format(e))

    return None


# Return True if captcha was succesfully solved
def automatic_captcha_solve(args, status, api, captcha_url, account, wh_queue):
    status['message'] = (
        'Account {} is encountering a captcha, starting 2captcha ' +
        'sequence.').format(account['username'])
    log.warning(status['message'])

    wh_message = {}
    if args.webhooks:
        wh_message = {'status_name': args.status_name,
                      'status': 'encounter',
                      'mode': '2captcha',
                      'account': account['username'],
                      'captcha': status['captcha'],
                      'time': 0}
        wh_queue.put(('captcha', wh_message))

    time_start = now()
    captcha_token = token_request(args, status, captcha_url)
    time_elapsed = now() - time_start

    if 'ERROR' in captcha_token:
        log.warning('Unable to resolve captcha, please check your ' +
                    '2captcha API key and/or wallet balance.')
        if args.webhooks:
            wh_message['status'] = 'error'
            wh_message['time'] = time_elapsed
            wh_queue.put(('captcha', wh_message))

        return False
    else:
        status['message'] = (
            'Retrieved captcha token, attempting to verify challenge ' +
            'for {}.').format(account['username'])
        log.info(status['message'])

        response = api.verify_challenge(token=captcha_token)
        time_elapsed = now() - time_start
        if 'success' in response['VERIFY_CHALLENGE']:
            status['message'] = "Account {} successfully uncaptcha'd.".format(
                account['username'])
            log.info(status['message'])
            if args.webhooks:
                wh_message['status'] = 'success'
                wh_message['time'] = time_elapsed
                wh_queue.put(('captcha', wh_message))

            return True
        else:
            status['message'] = (
                'Account {} failed verifyChallenge, putting away ' +
                'account for now.').format(account['username'])
            log.info(status['message'])
            if args.webhooks:
                wh_message['status'] = 'failure'
                wh_message['time'] = time_elapsed
                wh_queue.put(('captcha', wh_message))

            return False

def token_request(args, status, url):
    s = requests.Session()
    # Fetch the CAPTCHA_ID from 2captcha.
    try:
        request_url = (
            'http://2captcha.com/in.php?key={}&method=userrecaptcha' +
            '&googlekey={}&pageurl={}').format(args.captcha_key,
                                               args.captcha_dsk, url)
        captcha_id = s.post(request_url).text.split('|')[1]
        captcha_id = str(captcha_id)
    # IndexError implies that the retuned response was a 2captcha error.
    except IndexError:
        return 'ERROR'
    status['message'] = (
        'Retrieved captcha ID: {}; now retrieving token.').format(captcha_id)
    log.info(status['message'])
    # Get the response, retry every 5 seconds if it's not ready.
    recaptcha_response = s.get(
        'http://2captcha.com/res.php?key={}&action=get&id={}'.format(
            args.captcha_key, captcha_id)).text
    while 'CAPCHA_NOT_READY' in recaptcha_response:
        log.info('Captcha token is not ready, retrying in 5 seconds...')
        time.sleep(5)
        recaptcha_response = s.get(
            'http://2captcha.com/res.php?key={}&action=get&id={}'.format(
                args.captcha_key, captcha_id)).text
    token = str(recaptcha_response.split('|')[1])
    return token
