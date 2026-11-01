"""Bench content for the three plan templates: short, medium and long plans with only needed content.

short   진로체험 주간 (5 days, 4 activities)
medium  학교 체육대회 (1 day, preparation + 6 events)
long    연간 독서교육 사업 (12 months, 4 tasks, many milestones)
Unknown dates, headcounts and amounts stay marked 미정. Writes <template>-<size>.json into the target folder.
"""
import json
import sys
from pathlib import Path

T = lambda *xs: [{'text': x} for x in xs]


def plan(topic):
    """Shape one topic into the input fields of each template."""
    s = topic
    areas = s.get('areas') or [s['tasks'][0]]
    support = s.get('support_task') or s['tasks'][1]
    school = {
        'title': s['title'], 'organization': '학교명 미정 · ' + s['owner_dept'],
        'sections': {'activities': [{**({'heading': t['title']} if len(areas) > 1 else {}), 'activity_goal': t['goal'],
                                     'audience': t.get('audience', s['audience']), 'location': t.get('location', s['location']),
                                     'activities': T(*t.get('activities', t['details']))} for t in areas]},
        'preparation_goal': s['prep_goal'], 'period': s['period'], 'support': s['support'], 'owner': s['owners'],
        'safety': s['safety'], 'budget': s['budget'], 'evaluation': s['evaluation'],
        **{f'stage_{i + 1}': st[0] for i, st in enumerate(s['stages'][:4])},
        **{f'stage_{i + 1}_owner': st[1] for i, st in enumerate(s['stages'][:4])},
        'basis': T(*s['basis']), 'background': T(*s['background']), 'objectives': T(*s['objectives']),
        'principles': T(*s['principles']), 'checks': T(*s['checks']),
        'effects': T(*s['effects']),
    }
    education = {
        'subtitle': s['subtitle'], 'title': s['title'], 'publication_date': '2026년 작성 연월 미정', 'organization': '학교명 미정',
        'sections': {'activities': [{'task1_title': t['title'], 'period': t.get('period', s['period']), 'audience': t.get('audience', s['audience']),
                                     'method': t.get('method', t['content']), 'task1_goals': T(t['goal']), 'task1_details': T(*t['details'])} for t in areas]},
        'task2_title': support['title'], 'support_audience': s['support_audience'], 'support_budget': s['budget'],
        'task3_title': s['tasks'][-1]['title'], 'management_goal': s['management_goal'], 'owners': s['owners'],
        'management_budget': '미정(전체 예산 확정 후 편성)', 'evaluation_period': s['evaluation_period'],
        'basis': T(*s['basis']), 'objectives': T(*s['objectives']), 'status': T(*s['status']),
        'status_rows': s['status_rows'], 'principles': T(*s['principles']),
        'task2_goals': T(support['goal']), 'task2_details': T(*support['details']),
        'management': T(*s['checks']), 'evaluation': T(*s['eval_items']), 'follow_up': T(*s['follow_up']),
        'effects': T(*s['effects']),
    }
    tasks = s['tasks'] + [s['tasks'][-1]] * (3 - len(s['tasks']))
    project = {
        'title': s['title'], 'organization': '학교명 미정', 'subtitle': s['subtitle'], 'publication_date': '2026년 작성 연월 미정',
        'department': s['owner_dept'], 'current_state': s['status'][1], 'direction': s['direction'],
        'summary_schedule': s['summary_schedule'], 'background': s['background'][0],
        **{f'task{i + 1}_{k}': tasks[i][v] for i in range(3) for k, v in (('title', 'title'), ('goal', 'goal'), ('content', 'content'))},
        'project_overview': s['overview'], 'budget': s['budget'], 'period': s['period'], 'audience': s['audience'],
        'participation': s['support'], 'evaluation': s['evaluation'], 'evaluation_owner': s['evaluation_owner'],
        **{f'indicator_{i + 1}{x}': tasks[i]['indicators'][j] for i in range(3) for j, x in enumerate('ab')},
        **{f'role_{i + 1}': r for i, r in enumerate(s['roles'][:7])},
        'background_details': T(s['status'][0]),
        'task1_steps': T(*tasks[0]['steps']), 'task2_steps': T(*tasks[1]['steps']), 'task3_steps': T(*tasks[2]['steps']),
        'principles': T(*s['principles']), 'schedule_notes': T(s['schedule_note']),
        'milestones': [{'stage': a, 'work': b, 'when': c} for a, b, c in s['milestones']],
        'evaluation_details': T(s['eval_items'][0]), 'feedback': T(s['follow_up'][0]),
    }
    return {'plan-school': school, 'plan-education': education, 'plan-project': project}


SPORTS = dict(
    title='2026학년도 학교 체육대회 운영계획(안)', subtitle='함께 뛰고 응원하며 하나 되는 하루', owner_dept='체육 담당',
    goal='학년·학급이 함께 참여하는 종목으로 협동심과 건강한 생활 태도를 기른다.',
    audience='전교생 및 교직원(인원 미정), 학급 단위 참가', location='운동장(우천 시 체육관), 본부석은 운동장 동편',
    prep_goal='종목·심판·안전요원 배치와 학급별 연습 일정을 행사 2주 전까지 확정한다.',
    period='2026년 5월 중 하루(날짜 미정), 09:00~15:00', support='건강상 어려움이 있는 학생은 응원·기록 역할로 참여하고 보건실과 연계한다.',
    owners='체육 담당: 총괄·종목 운영 / 담임: 학급 인솔·지도 / 보건교사: 응급 대응 / 행정실: 물품·예산',
    safety='종목별 준비운동, 그늘막·식수 준비, 응급처치 구역 운영, 우천·폭염 시 일정 조정 기준을 사전 공지한다.',
    budget='물품·간식·상품비(금액 미정), 학교 운영비에서 편성 예정',
    evaluation='학생·교직원 설문으로 종목 구성과 운영 시간을 평가하고 다음 행사에 반영한다.',
    stages=[('사전 준비: 종목 확정, 심판·물품 준비', '체육 담당 / 2주 전'), ('학급 연습·안내: 출전 선수 확정, 가정 안내', '담임 / 1주 전'),
            ('대회 운영: 개회식·종목 경기·폐회식', '전 교직원 / 당일'), ('정리·평가: 설문, 물품 정리', '체육 담당 / 행사 후 1주')],
    basis=['2026학년도 학교 교육과정 및 학교 체육 운영 계획', '학교 행사 운영 안전 관리 지침'],
    background=['학년 간 교류 기회가 적어 학교 공동체 활동이 필요하다.', '건강 체력 증진을 위한 즐거운 신체 활동 경험이 요구된다.'],
    objectives=['협동 종목으로 학급 공동체 의식을 기른다.', '안전하게 즐기는 신체 활동 경험을 넓힌다.'],
    principles=['모든 학생이 한 종목 이상 참여하도록 종목을 구성한다.', '안전 수칙을 최우선으로 하고 무리한 경쟁을 지양한다.'],
    activities=['개회식 | 09:00~09:30 학생 대표 선서, 준비운동', '단체 줄넘기·줄다리기 | 학급 대항(학년별)', '이어달리기 | 학년별 남녀 혼성 계주',
                '공굴리기·장애물 경주 | 저학년 협동 종목', '학급 응원전 | 점심시간 후 학급별 3분 응원', '폐회식 | 15:00 시상, 정리 운동'],
    checks=['종목별 심판·기록 담당과 안전요원 배치를 확인한다.', '그늘막·식수·구급함 위치를 사전에 안내한다.', '우천·폭염 시 체육관 축소 운영안을 준비한다.'],
    effects=['학급·학년 간 협동과 소통이 늘어날 것으로 기대한다.', '즐거운 신체 활동 경험이 건강 생활 습관으로 이어지도록 한다.'],
    method='학급 대항 종목과 학년 혼합 종목을 섞어 운영',
    support_audience='전교생 및 운영 교직원(인원 미정)', management_goal='안전사고 없이 모든 학생이 참여하는 대회 운영',
    evaluation_period='행사 당일 관찰, 행사 후 1주 내 설문',
    status=['날짜·인원·예산은 미정이며, 아래 내용은 협의를 위한 운영안이다.', '학년 간 교류 행사가 적어 함께 참여하는 체육 활동이 필요함'],
    status_rows=[{'number': '1', 'audience': '전교생', 'owner': '체육 담당', 'activity': '학급 대항 종목', 'period': '오전', 'note': '학년별'},
                 {'number': '2', 'audience': '전교생', 'owner': '담임', 'activity': '응원전', 'period': '점심 후', 'note': '학급별 3분'},
                 {'number': '3', 'audience': '선발 학생', 'owner': '체육 담당', 'activity': '이어달리기', 'period': '오후', 'note': '혼성 계주'}],
    tasks=[dict(title='종목 운영', goal='모든 학생이 한 종목 이상 참여', content='학급 대항·협동 종목 6개 운영',
                details=['오전: 단체 줄넘기·줄다리기(학년별 학급 대항)', '오후: 이어달리기·장애물 경주, 학급 응원전'],
                steps=['오전: 학년별 학급 대항 종목 → 종목 기록표', '오후: 계주·협동 종목, 응원전 → 종합 기록표'], indicators=['종목별 참여 인원', '종목 기록표']),
           dict(title='안전·지원', goal='사고 없는 운영과 참여 지원', content='안전요원 배치, 응급처치 구역 운영',
                details=['사전: 안전 교육, 준비운동 영상 안내', '당일: 그늘막·식수·응급처치 구역 운영'],
                steps=['행사 전: 안전 교육과 동선 안내 → 안전 점검표', '행사 중: 응급처치 구역 운영 → 처치 기록'], indicators=['안전 점검표', '응급 처치 기록']),
           dict(title='평가·정리', goal='운영 결과를 다음 행사에 반영', content='설문과 협의로 개선점 정리',
                details=['행사 후 설문, 교직원 협의'], steps=['행사 후 1주: 설문·협의 → 개선 의견서'], indicators=['설문 결과', '개선 의견'])],
    areas=[dict(title='종목 운영', goal='학년·학급이 함께 참여하는 종목으로 협동심과 건강한 생활 태도를 기른다.', content='학급 대항·협동 종목 6개 운영',
                details=['오전: 단체 줄넘기·줄다리기(학년별 학급 대항)', '오후: 이어달리기·장애물 경주, 학급 응원전'],
                activities=['개회식 | 09:00~09:30 학생 대표 선서, 준비운동', '단체 줄넘기·줄다리기 | 학급 대항(학년별)', '이어달리기 | 학년별 남녀 혼성 계주',
                            '공굴리기·장애물 경주 | 저학년 협동 종목', '학급 응원전 | 점심시간 후 학급별 3분 응원', '폐회식 | 15:00 시상, 정리 운동'])],
    direction='학급 대항과 협동 종목을 섞고 안전 관리를 강화', summary_schedule='준비(2주 전) → 연습·안내(1주 전) → 대회(당일) → 평가(1주)',
    overview='전교생이 참여하는 하루 체육대회', evaluation_owner='체육 담당·학년부 공동 검토',
    roles=['체육 담당: 총괄·종목 운영', '담임: 학급 인솔·지도', '보건교사: 응급 대응', '행정실: 물품·예산', '학생회: 응원·진행 보조',
           '체육 담당: 가정 안내', '학교 내부 절차에 따라 시행·예산 확정'],
    schedule_note='날짜는 학사 일정과 날씨를 고려해 확정',
    milestones=[('준비', '종목 확정, 심판·물품 준비', '2주 전'), ('안내', '선수 확정, 가정 안내', '1주 전'), ('당일 오전', '개회식, 학급 대항 종목', '당일'),
                ('당일 오후', '계주, 응원전, 폐회식', '당일'), ('정리', '설문, 물품 정리', '행사 후 1주')],
    eval_items=['확인 자료: 종목 기록표, 안전 점검표, 설문 결과', '교직원 협의로 종목 구성과 시간 배정 개선점 정리'],
    follow_up=['환류: 설문 결과를 다음 학년도 체육대회 계획에 반영'],
)

READING = dict(
    title='2026학년도 연간 독서교육 운영계획(안)', subtitle='읽고 나누고 쓰는 한 해', owner_dept='독서교육 담당',
    goal='학년별 독서 활동을 연간으로 이어 읽기 습관과 생각을 나누는 힘을 기른다.',
    audience='전교생(학년별 인원 미정), 학급·동아리·도서관 단위 운영', location='학교도서관, 각 학급 교실, 시청각실(행사)',
    prep_goal='학기 시작 전 학년별 도서 목록과 활동 일정을 확정하고 도서관 자료를 정비한다.',
    period='2026년 3월~2027년 2월(연간), 학기별 세부 일정 미정', support='읽기 지원이 필요한 학생에게 오디오북·쉬운 글 자료와 짝 읽기를 제공한다.',
    owners='독서교육 담당: 총괄 / 사서교사: 도서·도서관 운영 / 담임: 학급 독서 / 국어과: 수업 연계',
    safety='도서관 이용 수칙과 행사 시 이동 동선을 안내하고, 외부 강사 행사는 사전 안전 점검을 한다.',
    budget='도서 구입비·행사 운영비(금액 미정), 학교 운영비와 도서관 예산에서 편성',
    evaluation='학기말 독서 기록과 설문, 도서 대출 현황으로 운영 결과를 확인하고 다음 학년도 계획에 반영한다.',
    stages=[('계획·준비: 도서 목록, 연간 일정 확정', '독서교육 담당 / 2월'), ('1학기 운영: 아침 독서, 한 학기 한 권', '담임·국어과 / 3~7월'),
            ('2학기 운영: 독서 축제, 작가 만남', '독서교육 담당 / 9~12월'), ('평가·환류: 설문, 결과 정리', '독서교육 담당 / 1~2월')],
    basis=['2026학년도 학교 교육과정 및 독서교육 운영 계획', '교육청 학교 독서교육 지원 계획(세부 공문 확인 후 반영)'],
    background=['스마트폰 사용 증가로 긴 글을 끝까지 읽는 경험이 줄고 있다.', '학년별 읽기 수준 차이가 커 단계별 지원이 필요하다.',
                '수업과 연계된 독서 활동을 연간으로 이어갈 체계가 필요하다.'],
    objectives=['매일 읽는 습관을 만들고 연간 독서 경험을 쌓는다.', '읽은 내용을 말과 글로 나누며 생각을 넓힌다.', '수업과 독서를 연계해 깊이 읽는 경험을 제공한다.'],
    principles=['학년별 수준과 관심을 고려해 도서를 고른다.', '읽은 양보다 읽는 과정과 나눔을 중시한다.', '학급·도서관·수업이 역할을 나누어 연계한다.'],
    activities=['아침 독서 | 매일 15분, 학급별 자율 도서 읽기', '한 학기 한 권 읽기 | 국어 수업과 연계한 깊이 읽기와 토론',
                '독서 동아리 | 월 2회 모임, 주제별 함께 읽기', '도서관 행사 | 학기별 북큐레이션 전시와 추천 도서 코너',
                '독서 축제 | 10월 중 5일, 독서 퀴즈·책 표지 그리기·낭독회', '작가와의 만남 | 2학기 1회, 학년별 강연과 질의응답',
                '독서 기록 | 학기별 독서 기록장 작성과 학급 공유', '가정 연계 | 방학 중 가족 함께 읽기 안내'],
    checks=['학년별 도서 목록과 수량을 학기 시작 전에 확인한다.', '아침 독서 시간 운영 상황을 월 1회 점검한다.', '행사 전 장소·물품·외부 강사 일정을 확인한다.',
            '읽기 지원이 필요한 학생의 자료 제공 여부를 학기별로 확인한다.', '도서 대출 현황을 분기별로 정리한다.'],
    effects=['매일 읽는 습관이 자리 잡고 독서량이 늘어날 것으로 기대한다.', '읽은 내용을 나누며 표현력과 사고력이 자랄 것으로 기대한다.',
             '수업과 연계한 독서로 깊이 읽는 경험이 넓어질 것으로 기대한다.'],
    method='학급 아침 독서, 수업 연계, 도서관 행사를 연간으로 연결',
    support_audience='전교생 및 운영 교원(인원 미정)', management_goal='학년별 독서 활동이 연간으로 끊기지 않도록 운영',
    evaluation_period='학기별 점검, 학년말 설문과 결과 정리',
    status=['운영 날짜·인원·예산은 미정이며, 아래 내용은 협의를 위한 운영안이다.', '긴 글을 끝까지 읽는 경험이 줄어 연간 독서 체계가 필요함'],
    status_rows=[{'number': str(i + 1), 'audience': a, 'owner': o, 'activity': act, 'period': p, 'note': n} for i, (a, o, act, p, n) in enumerate([
        ('전교생', '담임', '아침 독서', '연중', '매일 15분'), ('전교생', '국어과', '한 학기 한 권', '학기별', '수업 연계'),
        ('희망 학생', '사서교사', '독서 동아리', '월 2회', '주제별'), ('전교생', '독서교육 담당', '독서 축제', '10월', '5일간'),
        ('전교생', '독서교육 담당', '작가와의 만남', '2학기', '1회')])],
    tasks=[dict(title='매일 읽는 습관', goal='아침 독서와 독서 기록으로 읽기 습관 형성', content='아침 독서 15분, 학기별 독서 기록',
                details=['아침 독서: 매일 15분 학급별 자율 도서 읽기', '독서 기록: 학기별 독서 기록장 작성과 학급 공유', '가정 연계: 방학 중 가족 함께 읽기 안내'],
                steps=['3월: 학급별 아침 독서 시작 → 운영 점검표', '7월·12월: 독서 기록 공유 → 학급 기록 모음', '방학: 가족 함께 읽기 안내 → 가정 안내문'],
                indicators=['아침 독서 운영 점검표', '독서 기록장 작성']),
           dict(title='수업 연계 깊이 읽기', goal='한 학기 한 권 읽기로 깊이 읽기와 토론 경험', content='국어 수업 연계 한 학기 한 권 읽기',
                details=['도서 선정: 학년별 수준에 맞는 도서 3종 중 선택', '수업 운영: 읽기·토론·쓰기로 이어지는 단원 운영'],
                steps=['3~6월: 1학기 한 권 읽기 수업 → 토론 기록', '9~12월: 2학기 한 권 읽기 수업 → 서평 모음'], indicators=['토론 기록', '서평 작성']),
           dict(title='도서관·행사', goal='도서관 행사와 동아리로 함께 읽는 문화 확산', content='독서 동아리, 독서 축제, 작가와의 만남',
                details=['독서 동아리 월 2회, 북큐레이션 전시 학기별 운영', '10월 독서 축제 5일, 2학기 작가와의 만남 1회'],
                steps=['연중: 독서 동아리 월 2회 → 동아리 활동 기록', '10월: 독서 축제 5일 → 축제 결과 보고', '11월: 작가와의 만남 → 참여 소감'],
                indicators=['동아리 활동 기록', '행사 참여 소감']),
           dict(title='평가·환류', goal='연간 운영 결과를 다음 학년도에 반영', content='설문과 대출 현황 분석',
                details=['학년말 설문과 대출 현황 정리'], steps=['1~2월: 설문·결과 정리 → 연간 결과 보고'], indicators=['설문 결과', '대출 현황'])],
    areas=[dict(title='매일 읽는 습관', goal='아침 독서와 독서 기록으로 읽기 습관을 기른다.', content='아침 독서 15분, 학기별 독서 기록',
                method='학급 아침 독서와 학기별 독서 기록', location='각 학급 교실',
                details=['아침 독서: 매일 15분 학급별 자율 도서 읽기', '독서 기록: 학기별 독서 기록장 작성과 학급 공유', '가정 연계: 방학 중 가족 함께 읽기 안내']),
           dict(title='수업 연계 깊이 읽기', goal='국어 수업과 연계해 깊이 읽고 토론한다.', content='국어 수업 연계 한 학기 한 권 읽기',
                period='1·2학기(학기별)', audience='전교생(학년별)', method='국어 수업 단원 연계', location='각 학급 교실',
                details=['도서 선정: 학년별 수준에 맞는 도서 3종 중 선택', '수업 운영: 읽기·토론·쓰기로 이어지는 단원 운영']),
           dict(title='도서관·행사', goal='도서관 행사와 동아리로 함께 읽는 문화를 넓힌다.', content='독서 동아리, 독서 축제, 작가와의 만남',
                period='연중(축제 10월, 작가 만남 11월)', audience='전교생·희망 학생', method='동아리·행사 운영', location='학교도서관, 시청각실',
                details=['독서 동아리 월 2회, 학기별 북큐레이션 전시', '10월 독서 축제 5일(퀴즈·표지 그리기·낭독회)', '2학기 작가와의 만남 1회'])],
    support_task=dict(title='읽기 지원과 자료 준비', goal='모든 학생이 읽기 활동에 참여하도록 자료와 환경을 지원한다.',
                      details=['자료 준비: 학년별 도서 목록 확정, 도서관 자료 정비', '읽기 지원: 오디오북·쉬운 글 자료와 짝 읽기 제공']),
    direction='학급·수업·도서관 활동을 연간으로 연결하고 학기별로 점검',
    summary_schedule='계획(2월) → 1학기 운영(3~7월) → 2학기 운영(9~12월) → 평가(1~2월)',
    overview='전교생 대상 연간 독서교육(습관·수업 연계·행사)', evaluation_owner='독서교육 담당·국어과·사서교사 공동 검토',
    roles=['독서교육 담당: 총괄·행사 운영', '담임: 아침 독서·학급 기록', '국어과: 한 학기 한 권 수업', '사서교사: 도서 구입·도서관 운영',
           '학생 도서부: 행사 진행 보조', '독서교육 담당: 가정 안내', '학교 내부 절차에 따라 시행·예산 확정'],
    schedule_note='학기별 세부 일정은 학사 일정과 수업 시수를 고려해 확정',
    milestones=[('계획', '도서 목록·연간 일정 확정', '2월'), ('1학기 시작', '아침 독서 시작, 동아리 모집', '3월'), ('1학기 수업', '한 학기 한 권 읽기', '3~6월'),
                ('1학기 정리', '독서 기록 공유', '7월'), ('방학', '가족 함께 읽기 안내', '7~8월'), ('2학기 수업', '한 학기 한 권 읽기', '9~12월'),
                ('독서 축제', '퀴즈·표지 그리기·낭독회', '10월'), ('작가 만남', '학년별 강연', '11월'), ('2학기 정리', '독서 기록·서평 공유', '12월'),
                ('평가', '설문, 연간 결과 정리', '1~2월')],
    eval_items=['확인 자료: 독서 기록장, 토론 기록, 행사 소감, 대출 현황, 설문', '학년말 교원 협의로 활동 구성과 시기 개선점 정리'],
    follow_up=['환류: 설문과 대출 현황 분석 결과를 다음 학년도 계획에 반영'],
)


if __name__ == '__main__':
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    short_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None  # career-week JSONs written earlier
    for size, topic in (('medium', SPORTS), ('long', READING)):
        for template, values in plan(topic).items():
            (out / f'{template}-{size}.json').write_text(json.dumps(values, ensure_ascii=False, indent=1), encoding='utf-8')
    if short_dir:
        for name in ('school', 'education', 'project'):
            (out / f'plan-{name}-short.json').write_text((short_dir / f'{name}.json').read_text(encoding='utf-8'), encoding='utf-8')
    print(sorted(p.name for p in out.glob('*.json')))
