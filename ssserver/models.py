# django自带功能模块
from django.db import models
from django.conf import settings
from django.core import validators
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings

# python标准库
import datetime
import time
from random import choice
import base64

# 自己编写的脚本
from shadowsocks.tools import get_short_random_string

METHOD_CHOICES = (
    ('aes-256-cfb', 'aes-256-cfb'),
    ('aes-128-ctr', 'aes-128-ctr'),
    ('rc4-md5', 'rc4-md5'),
    ('salsa20', 'salsa20'),
    ('chacha20', 'chacha20'),
    ('none', 'none'),
)

PROTOCOL_CHOICES = (
    ('auth_sha1_v4', 'auth_sha1_v4'),
    ('auth_aes128_md5', 'auth_aes128_md5'),
    ('auth_aes128_sha1', 'auth_aes128_sha1'),
    ('auth_chain_a', 'auth_chain_a'),
    ('origin', 'origin'),
)


OBFS_CHOICES = (
    ('plain', 'plain'),
    ('http_simple', 'http_simple'),
    ('http_simple_compatible', 'http_simple_compatible'),
    ('http_post', 'http_post'),
    ('tls1.2_ticket_auth', 'tls1.2_ticket_auth'),
)

STATUS_CHOICES = (
    ('好用', '好用'),
    ('维护', '维护'),
    ('坏了', '坏了'),
)
# Create your models here.


class SSUser(models.Model):

    @classmethod
    def userTodyChecked(cls):
        '''返回今日签到人数'''
        return len([o for o in cls.objects.all() if o.get_check_in()])

    @classmethod
    def userNeverChecked(cls):
        '''返回从未签到过人数'''
        return len([o for o in cls.objects.all() if o.last_check_in_time.year == 1970])

    @classmethod
    def userNeverUsed(cls):
        '''返回从未使用过的人数'''
        return len([o for o in cls.objects.all() if o.last_use_time == 0])

    @classmethod
    def coreUser(cls):
        '''返回流量用的最多的前十名用户'''
        rec = {}
        for u in cls.objects.filter(download_traffic__gt=0):
            rec[u] = u.upload_traffic + u.download_traffic
        # 按照流量倒序排序，切片取出前十名
        rec = sorted(rec.items(), key=lambda rec: rec[1], reverse=True)[:10]
        return [(r[0], r[0].get_traffic()) for r in rec]

    @classmethod
    def randomPord(cls):
        '''从起始端口~最大端口随机找出一个没有用过的端口'''
        users = cls.objects.all()
        port_list = []
        for user in users:
            '''将所有端口都加入列表'''
            port_list.append(int(user.port))
        # 生成从最小到最大的断口池
        all_ports = [i for i in range(1025, max(port_list) + 1)]
        try:
            # 随机返回一个没有没占用的端口（取差集）
            return choice(list(set(all_ports).difference(set(port_list))))
        except:
            return max(port_list) + 1

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ss_user'
    )

    last_check_in_time = models.DateTimeField(
        '最后签到时间',
        null=True,
        # 默认设置为时间戳开始的那天
        default=datetime.datetime.fromtimestamp(0),
        editable=False,
    )

    # shadowsocks 数据库表字段
    password = models.CharField(
        'Shadowsocks密码',
        max_length=32,
        # 当密码少于6位时报错
        validators=[validators.MinLengthValidator(6), ],
        default=get_short_random_string,
        db_column='passwd',
    )
    port = models.IntegerField(
        '端口',
        db_column='port',
        unique=True,
    )
    last_use_time = models.IntegerField(
        '最后使用时间',
        default=0,
        editable=False,
        help_text='时间戳',
        db_column='t'
    )
    upload_traffic = models.BigIntegerField(
        '上传流量',
        default=0,
        db_column='u'
    )
    download_traffic = models.BigIntegerField(
        '下载流量',
        default=0,
        db_column='d'
    )
    transfer_enable = models.BigIntegerField(
        '总流量',
        default=settings.DEFAULT_TRAFFIC,
        db_column='transfer_enable'
    )
    switch = models.BooleanField(
        '保留字段switch',
        default=True,
        db_column='switch',
    )
    enable = models.BooleanField(
        '开启与否',
        default=True,
        db_column='enable',
    )

    method = models.CharField(
        '加密类型', default=settings.DEFAULT_METHOD, max_length=32, choices=METHOD_CHOICES,)

    protocol = models.CharField(
        '协议', default=settings.DEFAULT_PROTOCOL, max_length=32, choices=PROTOCOL_CHOICES,)

    obfs = models.CharField(
        '混淆', default=settings.DEFAULT_OBFS, max_length=32, choices=OBFS_CHOICES,)

    # 等级字段 和 shadowsocks.user 的level 同步
    level = models.PositiveIntegerField(
        '用户等级',
        default=0,)

    def __str__(self):
        return self.user.username

    def get_last_use_time(self):
        '''返回上一次的使用到时间'''
        return timezone.datetime.fromtimestamp(self.last_use_time)

    def get_traffic(self):
        '''返回用户使用的总流量GB '''
        return '{:.2f}'.format((self.download_traffic + self.upload_traffic) / settings.GB)

    def get_transfer(self):
        '''返回用户的总流量 GB'''
        return '{:.2f}'.format(self.transfer_enable / settings.GB)

    def get_unused_traffic(self):
        '''返回用户的剩余流量'''
        return '{:.2f}'.format((self.transfer_enable - self.upload_traffic - self.download_traffic) / settings.GB)

    def get_used_percentage(self):
        '''返回用户的为使用流量百分比'''
        try:
            return '{:.2f}'.format((self.download_traffic + self.upload_traffic) / self.transfer_enable * 100)
        except ZeroDivisionError:
            return '100'

    def get_check_in(self):
        '''返回当天是否签到'''
        # 获取当天日期
        check_day = self.last_check_in_time.day
        now_day = datetime.datetime.now().day
        return check_day == now_day

    def clean(self):
        '''保证端口在1024<50000之间'''
        if self.port:
            if not 1024 < self.port < 50000:
                raise ValidationError('端口必须在1024和50000之间')
        else:
            max_port_user = SSUser.objects.order_by('-port').first()
            if max_port_user:
                self.port = max_port_user.port + choice([2, 3])
            else:
                self.port = settings.START_PORT

    class Meta:
        verbose_name_plural = 'SS账户'
        ordering = ('-last_check_in_time',)
        db_table = 'user'


class TrafficLog(models.Model):
    '''用户流量记录'''

    @classmethod
    def totalTraffic(cls, node_id):
        '''返回该节点使用总流量 单位GB'''
        traffics = cls.objects.filter(node_id=node_id)
        total_traffic = sum(
            [u.upload_traffic + u.download_traffic for u in traffics])
        return round(total_traffic / settings.GB, 2)

    @classmethod
    def getUserTraffic(cls, node_id, user_id):
        '''返回指定用户对应节点的流量 单位GB'''
        traffics = cls.objects.filter(node_id=node_id, user_id=user_id)
        total_traffic = sum(
            [u.upload_traffic + u.download_traffic for u in traffics])
        return round(total_traffic / settings.GB, 2)

    @classmethod
    def getTrafficByDay(cls, node_id, user_id, date):
        '''返回指定用户对应节点对应日期的流量 单位GB'''
        traffics = cls.objects.filter(
            node_id=node_id, user_id=user_id, log_date__year=date.year, log_date__month=date.month, log_date__day=date.day)
        total_traffic = sum(
            [u.upload_traffic + u.download_traffic for u in traffics])
        return round(total_traffic / settings.GB, 2)

    user_id = models.IntegerField('用户id', blank=False, null=False)
    node_id = models.IntegerField('节点id', blank=False, null=False)
    upload_traffic = models.BigIntegerField(
        '上传流量',
        default=0,
        db_column='u'
    )
    download_traffic = models.BigIntegerField(
        '下载流量',
        default=0,
        db_column='d'
    )
    rate = models.FloatField('流量比例', default=1.0, null=False)
    traffic = models.CharField('流量记录', max_length=32, null=False)
    log_time = models.IntegerField('日志时间', blank=False, null=False)
    log_date = models.DateTimeField(
        '记录日期', default=timezone.now, blank=False, null=False)

    def __str__(self):
        return self.traffic

    class Meta:
        verbose_name_plural = '流量记录'
        ordering = ('-log_time',)
        db_table = 'user_traffic_log'


class Node(models.Model):
    '''线路节点'''
    @classmethod
    def get_sub_code(cls, user):
        '''获取该用户的所有节点链接'''
        ss_user = user.ss_user
        sub_code = ''
        node_list = cls.objects.filter(level__lte=user.level, show='显示')
        for node in node_list:
            sub_code = sub_code + node.get_ssr_link(ss_user) + "\n"
        return sub_code

    node_id = models.IntegerField('节点id', unique=True,)

    name = models.CharField('名字', max_length=32,)

    server = models.CharField('服务器IP', max_length=128,)

    method = models.CharField(
        '加密类型', default=settings.DEFAULT_METHOD, max_length=32, choices=METHOD_CHOICES,)

    custom_method = models.SmallIntegerField(
        '自定义加密',
        choices=(
            (0, 0),
            (1, 1)),
        default=0,
    )
    traffic_rate = models.FloatField(
        '流量比例',
        default=1.0
    )

    protocol = models.CharField(
        '协议', default=settings.DEFAULT_PROTOCOL, max_length=32, choices=PROTOCOL_CHOICES,)

    obfs = models.CharField(
        '混淆', default=settings.DEFAULT_OBFS, max_length=32, choices=OBFS_CHOICES,)

    info = models.CharField('节点说明', max_length=1024, blank=True, null=True,)

    status = models.CharField(
        '状态', max_length=32, default='ok', choices=STATUS_CHOICES,)

    level = models.PositiveIntegerField(
        '节点等级',
        default=0,
        validators=[
            MaxValueValidator(9),
            MinValueValidator(0),
        ]
    )

    show = models.CharField(
        '是否显示',
        max_length=32,
        choices=(
            ('显示', '显示'),
            ('不显示', '不显示')),
        default='显示',
    )

    group = models.CharField(
        '分组名', max_length=32, default='谜之屋')

    def __str__(self):
        return self.name

    def get_ssr_link(self, ss_user):
        '''返回ssr链接'''
        ssr_password = base64.urlsafe_b64encode(
            bytes(ss_user.password, 'utf8')).decode('ascii')
        ssr_remarks = base64.urlsafe_b64encode(
            bytes(self.name, 'utf8')).decode('ascii')
        ssr_group = base64.urlsafe_b64encode(
            bytes(self.group, 'utf8')).decode('ascii')
        if self.custom_method == 1:
            ssr_code = '{}:{}:{}:{}:{}:{}/?remarks={}&group={}'.format(
                self.server, ss_user.port, ss_user.protocol, ss_user.method, ss_user.obfs, ssr_password, ssr_remarks, ssr_group)
        else:
            ssr_code = '{}:{}:{}:{}:{}:{}/?remarks={}&group={}'.format(
                self.server, ss_user.port, self.protocol, self.method, self.obfs, ssr_password, ssr_remarks, ssr_group)
        ssr_pass = base64.urlsafe_b64encode(
            bytes(ssr_code, 'utf8')).decode('ascii')
        ssr_link = 'ssr://{}'.format(ssr_pass)
        return ssr_link

    def get_ss_link(self, ss_user):
        '''返回ss链接'''
        if self.custom_method == 1:
            ss_code = '{}:{}@{}:{}'.format(
                ss_user.method, ss_user.password, self.server, ss_user.port)
        else:
            ss_code = '{}:{}@{}:{}'.format(
                self.method, ss_user.password, self.server, ss_user.port)
        ss_pass = base64.urlsafe_b64encode(
            bytes(ss_code, 'utf8')).decode('ascii')
        ss_link = 'ss://{}'.format(ss_pass)
        return ss_link

    class Meta:
        ordering = ['id']
        verbose_name_plural = '节点'
        db_table = 'ss_node'


class NodeInfoLog(models.Model):
    '''节点负载记录'''

    node_id = models.IntegerField('节点id', blank=False, null=False)

    uptime = models.FloatField('更新时间', blank=False, null=False)

    load = models.CharField('负载', max_length=32, blank=False, null=False)

    log_time = models.IntegerField('日志时间', blank=False, null=False)

    def __str__(self):
        return str(self.node_id)

    class Meta:
        verbose_name_plural = '节点日志'
        db_table = 'ss_node_info_log'
        ordering = ('-log_time',)


class NodeOnlineLog(models.Model):
    '''节点在线记录'''

    @classmethod
    def totalOnlineUser(cls):
        '''返回所有节点的在线人数总和'''
        return sum([o.get_online_user() for o in cls.objects.all()])

    node_id = models.IntegerField('节点id', blank=False, null=False)

    online_user = models.IntegerField('在线人数', blank=False, null=False)

    log_time = models.IntegerField('日志时间', blank=False, null=False)

    def __str__(self):
        return '节点：{}'.format(self.node_id)

    def get_oneline_status(self):
        '''检测是否在线'''
        if int(time.time()) - self.log_time > 75:
            return False
        else:
            return True

    def get_online_user(self):
        '''返回在线人数'''
        if self.get_oneline_status() == True:
            return self.online_user
        else:
            return 0

    class Meta:
        verbose_name_plural = '节点在线记录'
        db_table = 'ss_node_online_log'
