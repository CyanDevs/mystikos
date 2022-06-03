library "OpenEnclaveJenkinsLibrary@${params.OECI_LIB_VERSION}"

pipeline {
    agent {
        label 'ACC-1804-DC4'
    }
    options {
        timeout(time: 360, unit: 'MINUTES')
    }
    parameters {
        string(name: "MYST_VERSION", description: "Mystikos release version (Example: 0.5.0). See https://github.com/deislabs/mystikos/releases for release versions")
        string(name: "REPOSITORY_NAME", defaultValue: "deislabs/mystikos", description: "GitHub repository to checkout")
        string(name: "BRANCH_NAME", defaultValue: "master", description: "The branch used to checkout the repository")
        string(name: "MYST_BASE_CONTAINER_TAG", defaultValue: "", description: "The tag for the new Mystikos base Docker container.")
        string(name: "OE_BASE_CONTAINER_TAG", defaultValue: "", description: "The tag for the base OE Docker container.")
        string(name: "INTERNAL_REPO", defaultValue: "https://mystikos.azurecr.io", description: "Url for internal Docker repository")
        string(name: "INTERNAL_REPO_CRED_ID", defaultValue: 'mystikos-internal-container-registry', description: "Credential ID for internal Docker repository")
        string(name: "OECI_LIB_VERSION", defaultValue: 'master', description: 'Version of OE Libraries to use')
        booleanParam(name: "PUBLISH_INTERNAL", defaultValue: false, description: "Publish container to internal registry?")
        booleanParam(name: "PUBLISH_DOCKER_HUB", defaultValue: false, description: "Publish container to Docker Hub?")
        booleanParam(name: "PUBLISH_VERSION_FILE", defaultValue: false, description: "Publish versioning information?")
    }
    environment {
        INTERNAL_REPO_CREDS = "${params.INTERNAL_REPO_CRED_ID}"
        BASE_DOCKERFILE_DIR = ".jenkins/docker/base/"
    }
    stages {
        stage("Checkout") {
            steps {
                cleanWs()
                checkout([$class: 'GitSCM',
                    branches: [[name: BRANCH_NAME]],
                    extensions: [],
                    userRemoteConfigs: [[url: "https://github.com/${params.REPOSITORY_NAME}"]]])
            }
        }
        stage('Build base container') {
            steps {
                dir(env.BASE_DOCKERFILE_DIR) {
                    script {
                        TAG_BASE_IMAGE = params.BASE_DOCKER_TAG ?: helpers.get_date(".") + "${BUILD_NUMBER}"
                    }
                    sh """
                        chmod +x ./build.sh
                        mkdir build
                        cd build
                        ../build.sh -m "${params.MYST_VERSION}" -o "${params.OE_BASE_CONTAINER_TAG}" -u "18.04" -t "${TAG_BASE_IMAGE}"
                        ../build.sh -m "${params.MYST_VERSION}" -o "${params.OE_BASE_CONTAINER_TAG}" -u "20.04" -t "${TAG_BASE_IMAGE}"
                    """
                }
            }
        }
        stage('Push base containers to internal repository') {
            when {
                expression { return params.PUBLISH_INTERNAL }
            }
            steps {
                script {
                    tag_bionic = "mystikos-bionic:${params.MYST_BASE_CONTAINER_TAG}"
                    tag_focal = "mystikos-focal:${params.MYST_BASE_CONTAINER_TAG}"
                    docker.withRegistry(params.INTERNAL_REPO, env.INTERNAL_REPO_CREDS) {
                        base_1804_image = docker.image(tag_bionic)
                        base_2004_image = docker.image(tag_focal)
                        common.exec_with_retry { base_1804_image.push() }
                        common.exec_with_retry { base_2004_image.push() }

                        if ( params.MYST_BASE_CONTAINER_TAG != 'latest' ) {
                            common.exec_with_retry { base_1804_image.push('latest') }
                            common.exec_with_retry { base_2004_image.push('latest') }
                        }
                    }
                    sh "docker logout ${params.INTERNAL_REPO}"
                }
            }
        }
        stage('Publish to Docker Hub') {
            when {
                expression {
                    return params.PUBLISH_DOCKER_HUB
                }
            }
            steps {
                script {
                    docker.withRegistry('', DOCKERHUB_REPO_CREDS) {
                        common.exec_with_retry { base_1804_image.push() }
                        common.exec_with_retry { base_1804_image.push() }
                        if ( params.MYST_BASE_CONTAINER_TAG != 'latest' ) {
                            common.exec_with_retry { base_1804_image.push('latest') }
                            common.exec_with_retry { base_2004_image.push('latest') }
                        }
                    }
                }
                sh "docker logout"
            }
        }
        stage('Publish info') {
            when {
                expression {
                    return params.PUBLISH_VERSION_FILE
                }
            }
            steps {
                script {
                    BASE_2004_PSW  = helpers.dockerGetAptPackageVersion("${tag_focal}", "libsgx-enclave-common")
                    BASE_2004_DCAP = helpers.dockerGetAptPackageVersion("${tag_focal}", "libsgx-ae-id-enclave") 
                    BASE_1804_PSW  = helpers.dockerGetAptPackageVersion("${tag_bionic}", "libsgx-enclave-common")
                    BASE_1804_DCAP = helpers.dockerGetAptPackageVersion("${tag_bionic}", "libsgx-ae-id-enclave")
                    sh """#!/bin/bash
                        cat <<EOF >>DOCKER_IMAGES.md
| Base Ubuntu 20.04 | ${TAG_BASE_IMAGE} | ${params.MYST_VERSION} | ${BASE_2004_PSW} | ${BASE_2004_DCAP} |
| Base Ubuntu 18.04 | ${TAG_BASE_IMAGE} | ${params.MYST_VERSION} | ${BASE_1804_PSW} | ${BASE_1804_DCAP} |
EOF
                    """
                }
                withCredentials([usernamePassword(credentialsId: 'github-oeciteam-user-pat',
                                 usernameVariable: 'GIT_USERNAME',
                                 passwordVariable: 'GIT_PASSWORD')]) {
                    sh '''
                        git config --global user.email "${GIT_USERNAME}@microsoft.com"
                        git config --global user.name ${GIT_USERNAME}
                        git checkout -B "oeciteam/publish-docker"
                        git add DOCKER_IMAGES.md
                        git commit -sm "Publish Docker Images"
                        git push --force https://${GIT_PASSWORD}@github.com/deislab/mystikos.git HEAD:oeciteam/publish-docker
                    '''
                }
            }
        }
    }
}
