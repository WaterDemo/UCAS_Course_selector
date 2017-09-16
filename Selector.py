from configparser import RawConfigParser
import requests
import re, json
from bs4 import BeautifulSoup
import time


class Selector():
    def __init__(self):
        self.course = []
        self.__courseConfig()
        conf = RawConfigParser()
        conf.read('config')
        self.prepareState = False
        self.__login = False
        # self.deptids = []
        self.username = conf.get('info', 'username')
        self.password = conf.get('info', 'passwd')
        self.update = conf.getboolean('info', 'update')
        self.delay_time = int(conf.get('time', 'time'))
        self.deptids = eval(conf.get('optim', 'depids'))
        self.course_dict = {}  # represent for all courses dict eg: {courseid: [courseNumber,depid] }
        self.s_token = None

        self.repeat_course = []

        self.baseUrl = 'http://sep.ucas.ac.cn'
        self.baseCourse = 'http://jwxk.ucas.ac.cn'
        self.loginUrl = 'http://sep.ucas.ac.cn/slogin'
        self.selectCourse = 'http://sep.ucas.ac.cn/portal/site/226/821'
        self.manageCourse = 'http://jwxk.ucas.ac.cn/courseManage/main'

        self.identity_pattern = '(http://jwxk.ucas.ac.cn/login\?Identity=.*?)"'

        self.header = {
            'Host': 'sep.ucas.ac.cn',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/60.0.3112.113 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.8,en;q=0.6'
        }
        self.s = requests.Session()

    def __courseConfig(self):
        with open('courseId', 'r') as infile:
            curs = infile.readlines()
            for line in curs:
                line = line.strip().split()
                if len(line) == 2:
                    self.course.append([line[0], '1'])
                    # self.course[line[0]] = True
                elif len(line) == 1:
                    self.course.append([line[0], '0'])
                    # self.course[line[0]] = False

    def login(self):
        content = {
            'userName': self.username,
            'pwd': self.password,
            'sb': 'sb',
        }
        self.s.post(self.loginUrl, data=content, headers=self.header)
        if 'sepuser' in self.s.cookies.get_dict():
            print('login success')
            self.__login = True
            return True
        return False

    def __parse_course(self, content):
        soup = BeautifulSoup(content, "html.parser")
        m_courseids = soup.body.find("form", class_="form-horizontal")
        depid = m_courseids.input['value']
        m_trs = m_courseids.find_all("tr")[1:]
        for i_tr in m_trs:
            td = i_tr.find_all("td")
            self.course_dict[td[2].text] = [td[0].input['value'], td[3].text, depid]

    def __parse_depid(self, content):
        print(self.deptids,'this is in deptids')
        if len(self.deptids) > 0:
            return
        saved_depids = {}
        soup = BeautifulSoup(content, "html.parser")
        m_depids = soup.body.find_all('div', recursive=False)[2].find_all('form')[1]
        p_divs = m_depids.find_all('div', recursive=False)
        for divs in p_divs:
            divs = divs.find_all('div')
            for div in divs:
                self.deptids.append(div.input['value'])
                saved_depids[div.input['value']] = div.text
        with open('depid.json', 'w') as outfile:
            outfile.write(json.dumps(saved_depids, indent=1, ensure_ascii=False))

    """
    this function's purpose:
    get related s token, this token may be defined as csrf token.
    the real request always looks as following:
    http://jwxk.ucas.ac.cn/courseManage/selectCourse?s=8ccafb90-de29-4b27-a0a0-2d362b279449
    """
    def __prepare(self):
        if self.__login:
            r = self.s.post(url=self.selectCourse, headers=self.header)
            res = re.findall(self.identity_pattern, r.text, re.S)
            # print('in function __prepare', res)
            if len(res) > 0:
                url = res[0]
                # important the Host in headers has changed!
                self.header['Host'] = 'jwxk.ucas.ac.cn'
                self.s.get(url=url, headers=self.header)  # necessary, redirection automatically, never forget
                resp = self.s.get(url=self.manageCourse, headers=self.header)
                pattern = '(/courseManage/selectCourse\?s=.*?)"'
                res = re.findall(pattern, resp.text)
                s_token = res[0].split('=')
                self.s_token = s_token[1]
                self.prepareState = True
                return True, s_token[1]
        return False, None

    def init_coursedict(self):
        state, s_token = self.__prepare()
        if state:
            if not self.update:
                with open('course.json', 'r') as infile:
                    self.course_dict = json.load(infile)
                return True
            resp = self.s.post(url=self.manageCourse, headers=self.header)  # may remove it? can not be done!!!
            self.__parse_depid(resp.text)
            dept_course_url = self.baseCourse + '/courseManage/selectCourse?s=' + s_token
            for depid in self.deptids:
                m_post = {
                    'deptIds': depid,
                    'sb': '0',
                }
                resp = self.s.post(url=dept_course_url, data=m_post, headers=self.header)

                self.__parse_course(resp.text)
            with open('course.json', 'w') as outfile:
                outfile.write(json.dumps(self.course_dict, indent=1, ensure_ascii=False))
            return True
        return False

    def __choose_course(self,m_course,enroll_course):
        the_course = self.course_dict[m_course[0]]
        xuewei = m_course[1]
        m_data = {
            'deptIds': the_course[2],
            'sids': the_course[0],
            'did_'+the_course[0]: the_course[0],
        }
        if xuewei==0:
            m_data.pop('did_'+the_course[0])
        resp = self.s.post(url=enroll_course, data=m_data, headers=self.header)
        return resp


    def enrollcourse(self):
        if self.__login:
            print('enroll course starting')
            enroll_course = self.baseCourse + '/courseManage/saveCourse?s=' + self.s_token
            # the_course = self.course_dict['092M2007H']
            for m_course in self.course:
                try:
                    resp = self.__choose_course(m_course, enroll_course)
                    # print(resp.text)
                    # 限选人数字段代表 人数限制
                    # 时间冲突字段代表 时间冲突
                    time_conflict = resp.text.find("时间冲突")
                    number_restrict = resp.text.find("限选人数")
                    if time_conflict > 0 or number_restrict > 0:
                        print('[选课失败]', self.course_dict[m_course[0]][1])
                        if number_restrict > 0 :
                            self.repeat_course.append(m_course)
                    else:
                        print("==============================================")
                        print("[选课成功]", self.course_dict[m_course[0]][1])
                        print("==============================================")
                except Exception as e :
                    print('[error]:', e, '这门课已选')
            while True:
                try:
                    for m_course in self.repeat_course:

                        print('[继续尝试]', self.course_dict[m_course[0]][1])
                        resp = self.__choose_course(m_course, enroll_course)
                        if resp.text.find("限选人数") > 0:
                            print("[限选人数]选课失败", self.course_dict[m_course[0]][1])
                            time.sleep(self.delay_time)
                        else:
                            print("==============================================")
                            print("选课成功", self.course_dict[m_course[0]][1])
                            print("==============================================")
                except Exception as err:
                    print(err)
                    break
        else:
            print('login failed error')

if __name__ == "__main__":
    selec = Selector()
    selec.login()
    selec.init_coursedict()
    selec.enrollcourse()
