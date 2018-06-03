from django.shortcuts import render, redirect, HttpResponse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from . import models
from .server import WSSHBridge, add_log

def login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password) # 得到一个User对象
        if user is not None:
            user_profile = models.UserProfile.objects.get(user=user) # 得到一个UserProfile对象
            if user_profile.enabled:
                auth_login(request, user) # django自带的session处理, 表示当前用户进入了, 将user保存到request信息中
                return redirect('/index/')
            else:
                message = "该用户已经被禁用, 请联系管理员"
                return render(request, 'fort/login.html', locals())
        else:
            message = "登入失败, 用户名或者密码错误!"
            return render(request, 'fort/login.html', locals())
    return render(request, 'fort/login.html', locals())

@login_required(login_url='/login/')
def logout(request):
    auth_logout(request) # django自带, 将当前用户登出
    return redirect('/login/')

# 没有登录的用户跳转到login
@login_required(login_url='/login/')
def index(request):
    remote_user_bind_hosts = models.RemoteUserBindHost.objects.filter(
        Q(enabled=True),
        Q(userprofile__user=request.user) |
        Q(group__userprofile__user=request.user)).distinct()


    return render(request, 'fort/index.html', locals())


@login_required(login_url='/login/')
def connect(request, user_bind_host_id):
    # 如果不是websocket请求则退出
    if not request.environ.get('wsgi.websocket'):
        return HttpResponse("错误, 非websocket请求!")
    try:
        remote_user_bind_host = models.RemoteUserBindHost.objects.filter(
            Q(enabled=True),
            Q(id=user_bind_host_id),
            Q(userprofile__user=request.user) | Q(group__userprofile__user=request.user)).distinct()[0]

    except Exception as e:
        message = "无效账户, 或者无权访问\n" + str(e)
        add_log(request.user, message, log_type='2')
        return HttpResponse("请求主机发生错误!")

    message = '来自{remote}的请求, 尝试连接 -> {username} @ {hostname} <{ip}: {port}>'.format(
        remote=request.META.get('REMOTE_ADDR'),
        username=remote_user_bind_host.remote_user.remote_user_name,
        hostname=remote_user_bind_host.host.host_name,
        ip=remote_user_bind_host.host.ip,
        port=remote_user_bind_host.host.port
    )
    print(message)
    add_log(request.user, message, log_type='0')

    bridge = WSSHBridge(request.environ.get('wsgi.websocket'), request.user)

    try:
        bridge.open(
            host_ip=remote_user_bind_host.host.ip,
            port=remote_user_bind_host.host.port,
            username=remote_user_bind_host.remote_user.remote_user_name,
            password=remote_user_bind_host.remote_user.password,
        )
    except Exception as e:
        message = "尝试连接{0}的过程中, 发生错误: \n {1}".format(
            remote_user_bind_host.remote_user.remote_user_name,e)
        print(message)
        add_log(request.user, message, log_type='2')
        return HttpResponse('错误! 无法建立SSH连接!')

    bridge.shell()
    request.environ.get('wsgi.websocket').close()
    print('用户断开连接.....')
    return HttpResponse('200,ok')

@login_required(login_url='/login/')
def get_log(request):
    if request.user.is_superuser:
        logs = models.AccessLog.objects.all()
        return render(request, 'fort/log.html', locals())
    else:
        add_log(request.user, "非超级用户尝试访问日志系统", log_type='4')
        return redirect('/index/')
