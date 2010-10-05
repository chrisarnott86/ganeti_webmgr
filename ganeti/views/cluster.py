import json
import os
import socket
import urllib2

from django import forms
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseNotFound, \
    HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext

from object_permissions import get_model_perms, get_user_perms, grant, revoke, \
    get_users
from object_permissions.views.permissions import ObjectPermissionFormNewUsers
from ganeti.models import *
from util.portforwarder import forward_port


@login_required
def detail(request, cluster_slug):
    """
    Display details of a cluster
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    vmlist = VirtualMachine.objects.filter(cluster__exact=cluster)
    return render_to_response("cluster.html", {
        'cluster': cluster,
        'user': request.user,
        'vmlist' : vmlist,
        },
        context_instance=RequestContext(request),
    )


def cluster_users(request, cluster_slug):
    """
    Display all of the users of a cluster
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    user = request.user
    if not (user.is_superuser or user.has_perm('admin', cluster)):
        return HttpResponseForbidden("You do not have sufficient privileges")
    
    users = get_users(cluster)
    
    return render_to_response("cluster/users.html",
                              {'cluster': cluster, 'users':users},
        context_instance=RequestContext(request),
    )


@login_required
def list(request):
    """
    List all clusters
    """
    cluster_list = Cluster.objects.all()
    return render_to_response("cluster_list.html", {
        'cluster_list': cluster_list,
        'user': request.user,
        },
        context_instance=RequestContext(request),
    )


def permissions(request, cluster_slug):
    """
    Update a users permissions.
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    user = request.user
    if not (user.is_superuser or user.has_perm('admin', cluster)):
        return HttpResponseForbidden("You do not have sufficient privileges")
    
    if request.method == 'POST':
        form = ObjectPermissionFormNewUsers(cluster, request.POST)
        if form.is_valid():
            form_user = form.cleaned_data['user']
            if form.update_perms():
                # return html to replace existing user row
                return render_to_response("cluster/user_row.html",
                                          {'cluster':cluster, 'user':form_user})
            else:
                # no permissions, send ajax response to remove user
                return HttpResponse('0', mimetype='application/json')
        
        # error in form return ajax response
        content = json.dumps(form.errors)
        return HttpResponse(content, mimetype='application/json')

    user_id = request.GET.get('user', None)
    if user_id:
        form_user = get_object_or_404(User, id=user_id)
        data = {'permissions':get_user_perms(form_user, cluster), \
                'user':user_id}
    else:
        data = {'permissions':[]}
    form = ObjectPermissionFormNewUsers(cluster, data)
    return render_to_response("cluster/permissions.html", \
                        {'form':form, 'cluster':cluster, 'user_id':user_id}, \
                        context_instance=RequestContext(request))


class QuotaForm(forms.Form):
    """
    Form for editing user quota on a cluster
    """
    user = forms.ModelChoiceField(queryset=User.objects.all())
    ram = forms.IntegerField(label='Memory (MB)', required=False, min_value=0)
    virtual_cpus = forms.IntegerField(label='Virtual CPUs', required=False, min_value=0)
    disk = forms.IntegerField(label='Disk Space (MB)', required=False, min_value=0)
    delete = forms.BooleanField(required=False, widget=forms.HiddenInput())


def quota(request, cluster_slug):
    """
    Updates quota for a user
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    user = request.user
    if not (user.is_superuser or user.has_perm('admin', cluster)):
        return HttpResponseForbidden("You do not have sufficient privileges")
    
    if request.method == 'POST':
        form = QuotaForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            form_user = data['user']
            delete = data['delete']
            if delete:
                # quota is deleted
                cluster.set_quota(form_user.get_profile(), None)
                return HttpResponse('1', mimetype='application/json')
            
            # quota is updated
            cluster.set_quota(form_user.get_profile(), data)
            return render_to_response("cluster/user_row.html",
                                  {'cluster':cluster, 'user':form_user})
        
        # error in form return ajax response
        content = json.dumps(form.errors)
        return HttpResponse(content, mimetype='application/json')

    user_id = request.GET.get('user', None)
    if user_id:
        form_user = get_object_or_404(User, id=user_id)
        quota = cluster.get_quota(form_user.get_profile())
        data = {'user':user_id}
        if quota:
            data.update(quota)
    else:
        return HttpResponseNotFound('User was not found')
        
    form = QuotaForm(data)
    return render_to_response("cluster/quota.html", \
                        {'form':form, 'cluster':cluster, 'user_id':user_id}, \
                        context_instance=RequestContext(request))