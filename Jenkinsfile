pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                sh 'ls -la'
            }
        }

        stage('Structure check') {
            steps {
                sh '''
                    for f in Dockerfile requirements.txt docker-compose.yml; do
                      test -f "stacks/gateway/$f" && echo "OK   $f"
                    done
                '''
            }
        }

        stage('Secret scan') {
            steps {
                sh '''
                    if git ls-files | grep -q "gateway/.env$"; then
                        echo "FAIL: .env is committed"
                        exit 1
                    fi
                    echo "OK   .env is not tracked"

                    if git log -p --all ':(exclude)Jenkinsfile' | grep -qE 'GATEWAY_TOKEN=[^[:space:]]{16,}'; then
                        echo "FAIL: token value in git history"
                        exit 1
                    fi
                    echo "OK   no token values in history"
                '''
            }
        }

        stage('Build gateway image') {
            steps {
                sh 'docker build -t atlas/gateway:ci-${BUILD_NUMBER} stacks/gateway'
                sh 'docker images atlas/gateway'
            }
        }
    }
}
