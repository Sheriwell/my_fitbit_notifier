import fitbit
from statistics import mean
from datetime import datetime
from dateutil.relativedelta import relativedelta
from ast import literal_eval
import math
import json
from linebot import LineBotApi
from linebot.models import TextSendMessage

class MyFitbitNotifier:
    
    def __init__(self):
        self.__set_authentications()      
        self.dict_step_objectives = {}
        self.__set_dates()
        self.__calc_days_on_the_q()
        self.__connect()
        self.__get_steps()
        
    def __set_authentications(self):
        self.FITBIT_OAUTH_TOKEN_FILE = "token.txt"
        self.__tokens                = open(self.FITBIT_OAUTH_TOKEN_FILE).read()
        self.__dict_tokens           = literal_eval(self.__tokens)
        self.__fitbit_access_token   = self.__dict_tokens['access_token']
        self.__fitbit_refresh_token  = self.__dict_tokens['refresh_token']
        
        self.CREDENTIAL_FILE         = "credentials.json"
        self.__JSON_CREDENTIALS      = json.loads(open(self.CREDENTIAL_FILE).read())
        self.__CLIENT_ID         = self.__JSON_CREDENTIALS["fitbit_client_id"]
        self.__CLIENT_SECRET     = self.__JSON_CREDENTIALS["fitbit_client_secret"]
        self.__LINE_ACCESS_TOKEN = self.__JSON_CREDENTIALS["line_access_token"]
        self.__LINE_MY_USER_ID   = self.__JSON_CREDENTIALS["line_my_user_id"]
        self.line_bot_api        = LineBotApi(channel_access_token=self.__LINE_ACCESS_TOKEN)
    
    def __update_token(self, token):
        f = open(self.FITBIT_OAUTH_TOKEN_FILE, 'w')
        f.write(str(token))
        f.close()
        return
    
    def __set_dates(self):
        today_temp = datetime.today()
        self.this_year  = today_temp.year
        self.this_month = today_temp.month
        self.this_date  = today_temp.day
        self.str_today = f'{self.this_year}-{str(self.this_month).zfill(2)}-{str(self.this_date).zfill(2)}'
        
        self.q_last_month = math.ceil(self.this_month / 3) * 3
        self.q_first_month = self.q_last_month - 2
        self.q_first_day = datetime(self.this_year, self.q_first_month, 1)
        self.q_last_day  = datetime(self.this_year, self.q_first_month, 1) + relativedelta(months=3) - relativedelta(days=1) 
        self.days_until_today = (datetime.today() - self.q_first_day).days + 1
    
    def __calc_days_on_the_q(self):
        # ALl days in this quarter
        all_days = (self.q_last_day - self.q_first_day).days + 1
        
        # Remaining days in this quarter including today
        remain_days = (self.q_last_day - datetime.today()).days + 2
        
        self.dict_days_on_the_q = {
            "remain_days": remain_days, 
            "all_days": all_days
        }
        
    def __connect(self):
        self.client = fitbit.Fitbit(
            self.__CLIENT_ID, 
            self.__CLIENT_SECRET,     
            access_token  = self.__fitbit_access_token, 
            refresh_token = self.__fitbit_refresh_token, 
            # refresh_cb    = self.__updateToken
            refresh_cb    = self.__update_token
        )
        
    def __get_steps(self):
        data_steps = self.client.time_series(
            'activities/steps',
            base_date = f"{self.this_year}-{str(self.q_first_month).zfill(2)}-01",
            end_date  = self.str_today
        )
        data_steps = data_steps['activities-steps']
        devnull_dummy = list(map(lambda x: x.update({"value_int":int(x["value"])}), data_steps))
        self.data_steps = data_steps
    
    def __return_arr_steps_value(self, data_steps, days_from, days_to):
        arr_steps_value = []
        for i in data_steps:
            arr_steps_value.append(i['value_int'])
        return arr_steps_value[days_from:len(data_steps)-days_to] 
    
    def __create_message(self):
        message = '' 
        for i in self.dict_step_objectives:
            if self.dict_step_objectives[i] > 0:
                if i == 0:
                    due='今日(1日) で'
                elif i == 1:
                    due='明日(2日) で'
                elif i == 999:
                    due="Q-Endに"
                else:
                    due=f'{i + 1}日で'
                message += f"{due}平均8000歩：毎日{self.dict_step_objectives[i]}歩が必要\n"
        return message[:-1]
    
    
    def calculate_step_objective(self, within_days):

        # 昨日までの合計歩数
        steps_till_yest = sum(self.__return_arr_steps_value(self.data_steps, days_from=0, days_to=1))
        
        for i in range(0,within_days):
            ### Q1 Adjustment
            steps_for_achivement = (self.days_until_today + i) * 8000
            delta_steps_for_8000 = steps_for_achivement - steps_till_yest
            # +1 is for today. 
            # if within_days = 0, which means you make avg.8000 within today, 1 should be the divider.
            # if within_days = 1, which means you make avg.8000 within tomorrow, 2 should be the divider - Today + Tomorrow.
            avg_steps_for_achv = round(delta_steps_for_8000 / (i + 1))
            self.dict_step_objectives.update({i:avg_steps_for_achv})
        
        ### Q1 Adjustment
        remain_required_steps = (self.dict_days_on_the_q['all_days'] * 8000) - steps_till_yest
        avg_steps_for_achv = math.ceil(remain_required_steps / self.dict_days_on_the_q['remain_days'])
        self.dict_step_objectives.update({999: avg_steps_for_achv})
        
    def push_average_steps(self, days_from):
        message1 = ''
        if len(self.data_steps) > 1:
            average_steps_yest = math.floor(mean(self.__return_arr_steps_value(self.data_steps, days_from=days_from, days_to=1)))
            message1 += f'昨日までの平均歩数: {average_steps_yest}歩\n'
            
        average_steps = math.floor(mean(self.__return_arr_steps_value(self.data_steps, days_from=days_from, days_to=0)))
        message2      = f'今日までの平均歩数: {average_steps}歩'
        
        message = f'{message1}{message2}'
        self.line_bot_api.push_message(self.__LINE_MY_USER_ID, messages=TextSendMessage(text=message))
        print(message)
    
    def push_say_something(self, custom_message):
        self.line_bot_api.push_message(self.__LINE_MY_USER_ID, messages=TextSendMessage(text=custom_message))
        print(custom_message)
        
    def push_steps_for_objective(self):
        message = self.__create_message()
        self.line_bot_api.push_message(self.__LINE_MY_USER_ID, messages=TextSendMessage(text=message))
        print(message)
        